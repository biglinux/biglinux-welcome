"""BigLinux Welcome — Installation flow shared by every page.

pre-checks → transaction preview → confirmation → job → feedback

The user always sees what will be installed (packages, dependencies,
download size, origin) before being asked for a password.
"""

from __future__ import annotations

import gettext
import threading
from collections.abc import Callable
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk
from install_backend import (
    STALE_DATABASE_DAYS,
    Failure,
    InstallJob,
    InstallManager,
    JobState,
    PackageInstallJob,
    PlasmoidInstallJob,
    PlasmoidSource,
    TransactionPreview,
    failure_message,
    format_size,
    is_network_available,
    is_pacman_locked,
    preview_install,
    sync_database_age_days,
)
from widgets import InstallPanel, show_alert

_ = gettext.gettext
ngettext = gettext.ngettext


@dataclass
class InstallRequest:
    """Something the user asked to install."""

    label: str
    icon: str = ""
    package: str = ""
    plasmoid: PlasmoidSource | None = None
    upgrade: bool = False
    repository: str = ""


def _toast(widget: Gtk.Widget, message: str) -> None:
    window = widget.get_root()
    if hasattr(window, "add_toast"):
        window.add_toast(message)


def request_install(
    widget: Gtk.Widget,
    request: InstallRequest,
    on_started: Callable[[InstallJob], None],
    on_not_started: Callable[[], None] | None = None,
) -> None:
    """Check, preview and confirm an installation, then start it.

    on_started(job) runs once the job is running; on_not_started() runs if
    the user declined or a pre-check failed."""

    def not_started() -> None:
        if on_not_started:
            on_not_started()

    manager = InstallManager.get_default()
    if manager.busy:
        show_alert(
            widget,
            _("Another installation is in progress"),
            _("Wait for the current installation to finish, then try again."),
        )
        not_started()
        return

    if not is_network_available():
        show_alert(
            widget,
            _("Could not install %s") % request.label,
            failure_message(Failure.OFFLINE),
        )
        not_started()
        return

    if request.plasmoid is not None:
        _confirm_plasmoid(widget, request, on_started, not_started)
        return

    if is_pacman_locked():
        show_alert(
            widget,
            _("Could not install %s") % request.label,
            failure_message(Failure.LOCKED),
        )
        not_started()
        return

    if request.upgrade:
        _confirm_upgrade(widget, request, on_started, not_started)
        return

    def worker() -> None:
        preview = preview_install(request.package, request.repository)
        age = sync_database_age_days()
        GLib.idle_add(
            _on_preview, widget, request, preview, age, on_started, not_started
        )

    threading.Thread(target=worker, daemon=True).start()


def _start(
    widget: Gtk.Widget,
    request: InstallRequest,
    job: InstallJob,
    on_started: Callable[[InstallJob], None],
    not_started: Callable[[], None],
) -> None:
    if not InstallManager.get_default().start(job):
        show_alert(
            widget,
            _("Another installation is in progress"),
            _("Wait for the current installation to finish, then try again."),
        )
        not_started()
        return
    job.connect("finished", lambda j: _announce_result(widget, request, j))
    on_started(job)


def _announce_result(
    widget: Gtk.Widget, request: InstallRequest, job: InstallJob
) -> None:
    messages = {
        JobState.SUCCEEDED: _("%s was installed successfully.") % request.label,
        JobState.CANCELLED: _("Installation of %s was cancelled.") % request.label,
        JobState.AUTH_CANCELLED: _(
            "Authentication was cancelled. Nothing was installed."
        ),
        JobState.FAILED: _("Could not install %s.") % request.label,
    }
    message = messages.get(job.state)
    if message:
        _toast(widget, message)


def _package_list(preview: TransactionPreview) -> Gtk.Widget:
    """Boxed list of the packages a transaction will install."""
    listbox = Gtk.ListBox()
    listbox.add_css_class("boxed-list")
    listbox.set_selection_mode(Gtk.SelectionMode.NONE)
    for name, version, repo, size in preview.packages:
        row = Adw.ActionRow(title=name, subtitle=f"{version} · {repo}")
        row.set_title_lines(1)
        size_label = Gtk.Label(label=format_size(size))
        size_label.add_css_class("dim-label")
        size_label.add_css_class("numeric")
        row.add_suffix(size_label)
        listbox.append(row)
    if len(preview.packages) <= 4:
        return listbox
    scroll = Gtk.ScrolledWindow()
    scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    scroll.set_max_content_height(240)
    scroll.set_propagate_natural_height(True)
    scroll.set_child(listbox)
    return scroll


def _on_preview(
    widget: Gtk.Widget,
    request: InstallRequest,
    preview: TransactionPreview,
    age_days: float | None,
    on_started: Callable[[InstallJob], None],
    not_started: Callable[[], None],
) -> bool:
    if preview.error:
        lower = preview.error.lower()
        if "target not found" in lower:
            body = failure_message(Failure.NOT_FOUND)
        elif "dependenc" in lower:
            body = failure_message(Failure.DEPENDENCIES)
        else:
            body = failure_message(Failure.UNKNOWN)
        show_alert(
            widget,
            _("Could not install %s") % request.label,
            f"{body}\n\n{preview.error}",
        )
        not_started()
        return GLib.SOURCE_REMOVE

    if preview.nothing_to_do:
        _toast(widget, _("%s is already installed.") % request.label)
        not_started()
        return GLib.SOURCE_REMOVE

    count = len(preview.packages)
    lines = [
        ngettext(
            "%(count)d package will be downloaded from the configured repositories (%(size)s).",
            "%(count)d packages will be downloaded from the configured repositories (%(size)s).",
            count,
        )
        % {"count": count, "size": format_size(preview.download_bytes)},
        _("You will be asked for the administrator password."),
    ]
    if age_days is not None and age_days > STALE_DATABASE_DAYS:
        days = int(age_days)
        lines.append(
            ngettext(
                "The package lists were last updated %d day ago. If the installation fails, update the system first.",
                "The package lists were last updated %d days ago. If the installation fails, update the system first.",
                days,
            )
            % days
        )

    dialog = Adw.AlertDialog(
        heading=_("Install %s?") % request.label,
        body="\n\n".join(lines),
    )
    dialog.set_extra_child(_package_list(preview))
    dialog.add_response("cancel", _("Cancel"))
    dialog.add_response("install", _("Install"))
    dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
    dialog.set_default_response("install")
    dialog.set_close_response("cancel")

    def on_response(_d: Adw.AlertDialog, response: str) -> None:
        if response != "install":
            not_started()
            return
        job = PackageInstallJob(
            request.package, request.label, repository=request.repository
        )
        _start(widget, request, job, on_started, not_started)

    dialog.connect("response", on_response)
    dialog.present(widget.get_root())
    return GLib.SOURCE_REMOVE


def _confirm_upgrade(
    widget: Gtk.Widget,
    request: InstallRequest,
    on_started: Callable[[InstallJob], None],
    not_started: Callable[[], None],
) -> None:
    def on_response(response: str) -> None:
        if response != "upgrade":
            not_started()
            return
        job = PackageInstallJob(
            request.package, request.label, upgrade=True, repository=request.repository
        )
        _start(widget, request, job, on_started, not_started)

    show_alert(
        widget,
        _("Update the system and install %s?") % request.label,
        _(
            "All installed packages will be updated before %s is installed. "
            "Updating everything together avoids partial upgrades, but it may "
            "take a while and download a large amount of data."
        )
        % request.label
        + "\n\n"
        + _("You will be asked for the administrator password."),
        [
            ("cancel", _("Cancel"), Adw.ResponseAppearance.DEFAULT),
            ("upgrade", _("Update and Install"), Adw.ResponseAppearance.SUGGESTED),
        ],
        on_response,
    )


def _confirm_plasmoid(
    widget: Gtk.Widget,
    request: InstallRequest,
    on_started: Callable[[InstallJob], None],
    not_started: Callable[[], None],
) -> None:
    source = request.plasmoid
    assert source is not None

    def on_response(response: str) -> None:
        if response != "install":
            not_started()
            return
        job = PlasmoidInstallJob(source, request.label)
        _start(widget, request, job, on_started, not_started)

    show_alert(
        widget,
        _("Install %s?") % request.label,
        _(
            "%s is a Plasma widget and is not available as a package. It will be "
            "downloaded from the official BigLinux repository on GitHub, checked "
            "against a known checksum and installed for your user only."
        )
        % request.label
        + "\n\n"
        + _("No administrator password is required.")
        + "\n\n"
        + source.url,
        [
            ("cancel", _("Cancel"), Adw.ResponseAppearance.DEFAULT),
            ("install", _("Install"), Adw.ResponseAppearance.SUGGESTED),
        ],
        on_response,
    )


def present_details(
    widget: Gtk.Widget,
    job: InstallJob,
    icon: str,
    on_open: Callable[[], None] | None = None,
) -> Adw.Dialog:
    """Show a job's live progress and log in a dialog."""
    dialog = Adw.Dialog()
    dialog.set_title(job.label)
    dialog.set_content_width(520)

    toolbar = Adw.ToolbarView()
    header = Adw.HeaderBar()
    header.set_show_title(False)
    toolbar.add_top_bar(header)

    panel = InstallPanel(job.label, icon)
    panel.set_margin_start(18)
    panel.set_margin_end(18)
    panel.set_margin_bottom(18)
    panel.set_open_callback(on_open)
    panel.set_done_callback(dialog.close)
    panel.bind_job(job)
    toolbar.set_content(panel)
    dialog.set_child(toolbar)
    dialog.connect("closed", lambda _d: panel.release())
    dialog.present(widget.get_root())
    return dialog


def offer_missing_app_install(
    widget: Gtk.Widget,
    label: str,
    package: str,
    icon: str,
    on_installed: Callable[[], None],
) -> None:
    """A launcher's application is missing: explain and offer to install it."""

    def worker() -> None:
        from install_backend import is_allowed_package, repo_packages

        info = (
            repo_packages([package]).get(package)
            if is_allowed_package(package)
            else None
        )
        GLib.idle_add(on_checked, info)

    def on_checked(info) -> bool:
        if info is None:
            show_alert(
                widget,
                _("%s is not installed") % label,
                _(
                    "The application is not installed and is not available in the configured repositories."
                ),
            )
            return GLib.SOURCE_REMOVE

        def on_response(response: str) -> None:
            if response != "install":
                return
            request = InstallRequest(label=label, icon=icon, package=package)
            request_install(
                widget,
                request,
                lambda job: present_details(widget, job, icon, on_open=on_installed),
            )

        show_alert(
            widget,
            _("%s is not installed") % label,
            _(
                "It is available in the configured repositories (package %(package)s, from %(repo)s). Do you want to install it now?"
            )
            % {"package": package, "repo": info.repository},
            [
                ("cancel", _("Not Now"), Adw.ResponseAppearance.DEFAULT),
                ("install", _("Install"), Adw.ResponseAppearance.SUGGESTED),
            ],
            on_response,
        )
        return GLib.SOURCE_REMOVE

    threading.Thread(target=worker, daemon=True).start()
