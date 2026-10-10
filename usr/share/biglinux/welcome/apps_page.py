"""BigLinux Welcome — "Applications to Install" page.

Each application is described in pages.yaml (page_type: "apps"):

    - label: "BigCam"
      description: "Manage webcams, video sources, and multimedia features…"
      icon: "applications/bigcam.svg"
      package: "bigcam"          # pacman package (must be allowlisted)
      command: "bigcam"          # how to open it once installed
    - label: "ChatAI"
      plasmoid: "ChatAI-Plasmoid" # Plasma widget id (see install_backend.PLASMOID_SOURCES)
"""

from __future__ import annotations

import enum
import gettext
import threading
from dataclasses import dataclass

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk, Pango
from install_backend import (
    N_,
    PLASMOID_SOURCES,
    Failure,
    InstallJob,
    InstallManager,
    JobState,
    add_plasmoid_to_panel,
    format_size,
    install_target,
    installed_packages,
    installed_plasmoid_version,
    is_plasma_session,
    is_plasmoid_in_panel,
    repo_packages,
)
from install_flow import InstallRequest, present_details, request_install
from widgets import (
    card_grid,
    command_available,
    launch_command,
    load_icon,
    make_heading,
    show_alert,
)

_ = gettext.gettext


@dataclass(frozen=True)
class AppEntry:
    """An application offered on the page."""

    label: str
    description: str = ""
    icon: str = ""
    package: str = ""
    command: str = ""
    plasmoid: str = ""
    repository: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> AppEntry:
        return cls(
            label=str(data.get("label", "")),
            description=str(data.get("description", "")),
            icon=str(data.get("icon", "")),
            package=str(data.get("package", "")),
            command=str(data.get("command", "")),
            plasmoid=str(data.get("plasmoid", "")),
            repository=str(data.get("repository", "")),
        )

    @property
    def target(self) -> str:
        """pacman target, pinned to the configured repository if any."""
        return install_target(self.package, self.repository)

    @property
    def is_plasmoid(self) -> bool:
        return bool(self.plasmoid)


class AppStatus(enum.Enum):
    CHECKING = "checking"
    NOT_INSTALLED = "not-installed"
    INSTALLING = "installing"
    INSTALLED = "installed"
    FAILED = "failed"
    UPDATE = "update"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class AppInfo:
    """Result of checking an application's state on this system."""

    status: AppStatus
    version: str = ""
    repository: str = ""
    download_size: str = ""
    in_panel: bool = False


def check_apps(entries: list[AppEntry]) -> dict[str, AppInfo]:
    """Find the real state of every entry. Blocking — run in a thread."""
    entries_with_package = [e for e in entries if e.package and e.target]
    installed = installed_packages({e.package for e in entries_with_package})
    available = repo_packages({e.target for e in entries_with_package})

    result: dict[str, AppInfo] = {}
    for entry in entries:
        if entry.is_plasmoid:
            source = PLASMOID_SOURCES.get(entry.plasmoid)
            installed_version = installed_plasmoid_version(entry.plasmoid)
            if not is_plasma_session() or source is None:
                status = AppStatus.UNSUPPORTED
            elif installed_version is None:
                status = AppStatus.NOT_INSTALLED
            elif source.version and installed_version != source.version:
                status = AppStatus.UPDATE
            else:
                status = AppStatus.INSTALLED
            result[entry.label] = AppInfo(
                status=status,
                version=installed_version or "",
                repository="GitHub",
                in_panel=status is AppStatus.INSTALLED
                and is_plasmoid_in_panel(entry.plasmoid),
            )
            continue

        repo = available.get(entry.target)
        if entry.package in installed:
            status = AppStatus.INSTALLED
        elif repo is None:
            status = AppStatus.UNAVAILABLE
        else:
            status = AppStatus.NOT_INSTALLED
        result[entry.label] = AppInfo(
            status=status,
            version=repo.version if repo else "",
            repository=repo.repository if repo else "",
            download_size=format_size(repo.download_bytes)
            if repo and repo.download_bytes
            else "",
        )
    return result


# Status pill texts (translated at use)
_STATUS_LABELS = {
    AppStatus.CHECKING: N_("Checking…"),
    AppStatus.NOT_INSTALLED: N_("Not installed"),
    AppStatus.INSTALLING: N_("Installing"),
    AppStatus.INSTALLED: N_("Installed"),
    AppStatus.FAILED: N_("Installation failed"),
    AppStatus.UPDATE: N_("Update available"),
    AppStatus.UNAVAILABLE: N_("Unavailable"),
    AppStatus.UNSUPPORTED: N_("Requires KDE Plasma"),
}


class AppCard(Gtk.Box):
    """Card with icon, name, description, live status and one main action.

    The card keeps the same size in every state: the title is one line, the
    description at most DESCRIPTION_LINES, and the footer is a homogeneous
    stack (idle / progress / failure pages share one height). Long texts are
    ellipsized; their full text is in the tooltip and in "Details"."""

    DESCRIPTION_LINES = 4
    TEXT_CHARS = 40

    WIDTH = 420

    def __init__(self, entry: AppEntry) -> None:
        super().__init__(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=18,
            accessible_role=Gtk.AccessibleRole.GROUP,
        )
        self.entry = entry
        self.label = _(entry.label)
        self.status = AppStatus.CHECKING
        self.info = AppInfo(AppStatus.CHECKING)
        self.job: InstallJob | None = None
        self._job_handlers: list[int] = []
        self._last_failure = Failure.NONE

        self.add_css_class("app-card")
        self.update_property(
            [Gtk.AccessibleProperty.LABEL, Gtk.AccessibleProperty.DESCRIPTION],
            [self.label, _(entry.description)],
        )

        # -- Icon with installed badge --
        overlay = Gtk.Overlay()
        overlay.set_valign(Gtk.Align.START)
        self.append(overlay)

        icon_bg = Gtk.Box()
        icon_bg.add_css_class("app-icon-bg")
        overlay.set_child(icon_bg)
        icon = load_icon(entry.icon or "application-x-executable", 64)
        icon_bg.append(icon)

        self._badge = Gtk.Box()
        self._badge.add_css_class("check-badge")
        self._badge.set_halign(Gtk.Align.END)
        self._badge.set_valign(Gtk.Align.END)
        self._badge.set_visible(False)
        check = Gtk.Image.new_from_icon_name("object-select-symbolic")
        check.set_pixel_size(12)
        self._badge.append(check)
        overlay.add_overlay(self._badge)

        # -- Text column --
        column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        column.set_hexpand(True)
        self.append(column)

        top = Gtk.Box(spacing=10)
        column.append(top)

        name = self._one_line_label(self.label, "app-card-title")
        name.set_hexpand(True)
        name.set_tooltip_text(self.label)
        top.append(name)

        # Status texts are short and fixed: never ellipsized (the title,
        # which has a tooltip, gives way instead)
        self._status_label = self._one_line_label("", "app-status")
        self._status_label.set_ellipsize(Pango.EllipsizeMode.NONE)
        self._status_label.set_valign(Gtk.Align.CENTER)
        self._status_label.set_halign(Gtk.Align.END)
        top.append(self._status_label)

        description = Gtk.Label(label=_(entry.description), xalign=0)
        description.add_css_class("app-card-description")
        description.set_wrap(True)
        description.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        description.set_lines(self.DESCRIPTION_LINES)
        description.set_max_width_chars(self.TEXT_CHARS)
        description.set_ellipsize(Pango.EllipsizeMode.END)
        description.set_tooltip_text(_(entry.description))
        description.set_valign(Gtk.Align.START)
        description.set_vexpand(True)
        column.append(description)

        # -- Footer: idle ↔ progress ↔ failure, all the same height --
        self._footer = Gtk.Stack()
        self._footer.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self._footer.set_transition_duration(200)
        self._footer.set_hhomogeneous(True)
        self._footer.set_vhomogeneous(True)
        self._footer.set_interpolate_size(False)
        column.append(self._footer)

        idle = Gtk.Box(spacing=8)
        idle.set_valign(Gtk.Align.END)
        self._meta_label = self._one_line_label("", "app-card-meta")
        self._meta_label.set_hexpand(True)
        idle.append(self._meta_label)

        self._action_btn = Gtk.Button()
        self._action_btn.add_css_class("pill")
        self._action_btn.add_css_class("app-action")
        self._action_btn.connect("clicked", self._on_action)
        idle.append(self._action_btn)

        self._spinner = Adw.Spinner()
        self._spinner.set_size_request(24, 24)
        self._spinner.set_visible(False)
        idle.append(self._spinner)
        self._footer.add_named(idle, "idle")

        progress = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        progress.set_valign(Gtk.Align.END)
        phase_row = Gtk.Box(spacing=8)
        self._phase_label = self._one_line_label("", "app-card-meta")
        self._phase_label.set_hexpand(True)
        phase_row.append(self._phase_label)
        self._percent_label = Gtk.Label(label="0%")
        self._percent_label.add_css_class("app-card-meta")
        self._percent_label.add_css_class("numeric")
        phase_row.append(self._percent_label)
        progress.append(phase_row)

        self._progress = Gtk.ProgressBar()
        self._progress.add_css_class("install-progress")
        self._progress.set_valign(Gtk.Align.CENTER)
        self._progress.set_hexpand(True)
        self._progress.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Installing %s") % self.label]
        )

        bar_row = Gtk.Box(spacing=4)
        bar_row.append(self._progress)
        buttons = Gtk.Box(spacing=2)
        bar_row.append(buttons)
        progress.append(bar_row)

        buttons.append(self._details_button())
        self._cancel_btn = Gtk.Button(label=_("Cancel"))
        self._cancel_btn.add_css_class("flat")
        self._cancel_btn.add_css_class("app-card-link")
        self._cancel_btn.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Cancel installation of %s") % self.label],
        )
        self._cancel_btn.connect("clicked", self._on_cancel)
        buttons.append(self._cancel_btn)
        self._footer.add_named(progress, "progress")

        failed = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        failed.set_valign(Gtk.Align.END)
        self._error_label = Gtk.Label(xalign=0)
        self._error_label.add_css_class("app-card-error")
        self._error_label.set_wrap(True)
        self._error_label.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self._error_label.set_lines(2)
        self._error_label.set_ellipsize(Pango.EllipsizeMode.END)
        # Small natural width: it wraps at the card's width instead of
        # widening it. Both lines are reserved up front, so an error never
        # makes the card taller either.
        self._error_label.set_max_width_chars(6)
        self._error_label.set_label("X\nX")
        self._error_label.set_size_request(
            -1, self._error_label.measure(Gtk.Orientation.VERTICAL, -1)[1]
        )
        self._error_label.set_label("")
        failed.append(self._error_label)
        retry_row = Gtk.Box(spacing=6)
        retry_row.set_halign(Gtk.Align.END)
        retry_row.append(self._details_button())
        self._retry_btn = Gtk.Button()
        self._retry_btn.add_css_class("pill")
        self._retry_btn.add_css_class("app-action")
        self._retry_btn.add_css_class("suggested-action")
        self._retry_btn.connect("clicked", self._on_action)
        retry_row.append(self._retry_btn)
        failed.append(retry_row)
        self._footer.add_named(failed, "failed")

        manager = InstallManager.get_default()
        self._busy_handler = manager.connect("busy-changed", self._on_busy_changed)
        self.set_status(AppStatus.CHECKING)

    @staticmethod
    def _one_line_label(text: str, css: str, max_chars: int = 6) -> Gtk.Label:
        """Single line, ellipsized. Its natural width is kept small so long
        texts never widen the card; it fills the free space via hexpand."""
        label = Gtk.Label(label=text, xalign=0)
        label.add_css_class(css)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_single_line_mode(True)
        label.set_max_width_chars(max_chars)
        return label

    def _details_button(self) -> Gtk.Button:
        button = Gtk.Button(label=_("Details"))
        button.add_css_class("flat")
        button.add_css_class("app-card-link")
        button.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Show installation details for %s") % self.label],
        )
        button.connect("clicked", self._on_details)
        return button

    # -- State --

    def apply_info(self, info: AppInfo) -> None:
        """Apply the result of check_apps() unless an install is running."""
        if self.status is AppStatus.INSTALLING:
            return
        if self.status is AppStatus.FAILED and info.status is AppStatus.NOT_INSTALLED:
            self.info = info
            self._update_meta()
            return
        self.info = info
        self.set_status(info.status)

    def set_status(self, status: AppStatus) -> None:
        self.status = status
        for s in AppStatus:
            self._status_label.remove_css_class(s.value)
        self._status_label.add_css_class(status.value)
        self._status_label.set_label(_(_STATUS_LABELS[status]))
        self._badge.set_visible(status is AppStatus.INSTALLED)
        self._spinner.set_visible(False)
        self._footer.set_visible_child_name(
            {AppStatus.INSTALLING: "progress", AppStatus.FAILED: "failed"}.get(
                status, "idle"
            )
        )
        if status is AppStatus.INSTALLING:
            self.add_css_class("installing")
        else:
            self.remove_css_class("installing")
        self._update_action()
        self._update_meta()
        self.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            [f"{_(_STATUS_LABELS[status])}. {_(self.entry.description)}"],
        )

    def _update_action(self) -> None:
        btn = self._action_btn
        btn.remove_css_class("suggested-action")
        btn.set_sensitive(True)
        btn.set_tooltip_text(None)
        visible = True
        status = self.status

        if self._last_failure is Failure.OUTDATED_DATABASE:
            self._retry_btn.set_label(_("Update and Install"))
        else:
            self._retry_btn.set_label(_("Try Again"))
        self._retry_btn.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Try again to install %s") % self.label]
        )
        busy = InstallManager.get_default().busy
        self._retry_btn.set_sensitive(not busy)
        self._retry_btn.set_tooltip_text(
            _("Another installation is in progress") if busy else None
        )

        if status is AppStatus.NOT_INSTALLED:
            btn.set_label(_("Install"))
            btn.add_css_class("suggested-action")
            accessible = _("Install %s") % self.label
        elif status is AppStatus.UPDATE:
            btn.set_label(_("Update"))
            btn.add_css_class("suggested-action")
            accessible = _("Update %s") % self.label
        elif status is AppStatus.INSTALLED and self.entry.is_plasmoid:
            if self.info.in_panel:
                btn.set_label(_("Added to Panel"))
                btn.set_sensitive(False)
            else:
                btn.set_label(_("Add to Panel"))
            accessible = _("Add %s to the panel") % self.label
        elif status is AppStatus.INSTALLED:
            btn.set_label(_("Open"))
            visible = bool(self.entry.command)
            accessible = _("Open %s") % self.label
        else:
            visible = False
            accessible = ""

        installing_elsewhere = busy and status in (
            AppStatus.NOT_INSTALLED,
            AppStatus.UPDATE,
        )
        if installing_elsewhere:
            btn.set_sensitive(False)
            btn.set_tooltip_text(_("Another installation is in progress"))

        btn.set_visible(visible)
        if accessible:
            btn.update_property([Gtk.AccessibleProperty.LABEL], [accessible])

    def _update_meta(self) -> None:
        info = self.info
        status = self.status
        if status is AppStatus.CHECKING:
            text = ""
        elif status is AppStatus.UNAVAILABLE:
            text = _("Not available in the configured repositories")
        elif status is AppStatus.UNSUPPORTED:
            text = _("Plasma widget for KDE Plasma 6")
        elif self.entry.is_plasmoid:
            text = _("Plasma widget")
        elif status is AppStatus.INSTALLED:
            text = info.repository
        elif info.download_size:
            text = f"{info.download_size} · {info.repository}"
        else:
            text = info.repository
        self._meta_label.set_label(text)
        self._meta_label.set_tooltip_text(text or None)

    def _on_busy_changed(self, _manager: InstallManager, _busy: bool) -> None:
        self._update_action()

    # -- Actions --

    def _on_action(self, _btn: Gtk.Button) -> None:
        status = self.status
        if status in (AppStatus.NOT_INSTALLED, AppStatus.FAILED, AppStatus.UPDATE):
            self._install(upgrade=self._last_failure is Failure.OUTDATED_DATABASE)
        elif status is AppStatus.INSTALLED:
            self._open()

    def _install(self, upgrade: bool = False) -> None:
        source = (
            PLASMOID_SOURCES.get(self.entry.plasmoid)
            if self.entry.is_plasmoid
            else None
        )
        request = InstallRequest(
            label=self.label,
            icon=self.entry.icon,
            package=self.entry.package,
            plasmoid=source,
            upgrade=upgrade,
            repository=self.entry.repository,
        )
        self._action_btn.set_visible(False)
        self._spinner.set_visible(True)
        request_install(self, request, self.bind_job, self._update_action_after_decline)

    def _update_action_after_decline(self) -> None:
        self._spinner.set_visible(False)
        self._update_action()

    def bind_job(self, job: InstallJob) -> None:
        self._unbind_job()
        self.job = job
        self._last_failure = Failure.NONE
        self._progress.set_fraction(job.fraction)
        self._percent_label.set_label(f"{int(job.fraction * 100)}%")
        self._phase_label.set_label(job.phase or _("Waiting for authentication…"))
        self._cancel_btn.set_sensitive(job.cancellable)
        self._job_handlers = [
            job.connect("progress", self._on_job_progress),
            job.connect("cancellable-changed", self._on_job_cancellable),
            job.connect("finished", self._on_job_finished),
        ]
        self.set_status(AppStatus.INSTALLING)

    def _unbind_job(self) -> None:
        if self.job is not None:
            for handler in self._job_handlers:
                self.job.disconnect(handler)
        self._job_handlers = []

    def _on_job_progress(self, _job: InstallJob, fraction: float, phase: str) -> None:
        self._progress.set_fraction(fraction)
        self._percent_label.set_label(f"{int(fraction * 100)}%")
        if phase:
            self._phase_label.set_label(phase)

    def _on_job_cancellable(self, _job: InstallJob, cancellable: bool) -> None:
        self._cancel_btn.set_sensitive(cancellable)
        if not cancellable:
            self._cancel_btn.set_tooltip_text(_("Cannot cancel during installation"))

    def _on_cancel(self, _btn: Gtk.Button) -> None:
        if self.job and self.job.cancel():
            self._cancel_btn.set_sensitive(False)
            self._phase_label.set_label(_("Cancelling installation…"))

    def _on_job_finished(self, job: InstallJob) -> None:
        self._unbind_job()
        if job.state is JobState.SUCCEEDED:
            self.info = AppInfo(
                AppStatus.INSTALLED,
                version=self.info.version,
                repository=self.info.repository,
                in_panel=getattr(job, "in_panel", False),
            )
            self.set_status(AppStatus.INSTALLED)
            self._action_btn.grab_focus()
        elif job.state is JobState.FAILED:
            self._last_failure = job.failure
            self._error_label.set_label(job.failure_text())
            self._error_label.set_tooltip_text(job.failure_text())
            self.set_status(AppStatus.FAILED)
            self._retry_btn.grab_focus()
        else:
            self.set_status(AppStatus.NOT_INSTALLED)

    def _on_details(self, _btn: Gtk.Button) -> None:
        if self.job is not None:
            present_details(self, self.job, self.entry.icon, on_open=None)

    def _open(self) -> None:
        if self.entry.is_plasmoid:
            self._add_to_panel()
            return
        command = self.entry.command
        try:
            launched = command_available(command)
            if launched:
                launch_command(command, self)
        except GLib.Error:
            launched = False
        if not launched:
            show_alert(
                self,
                _("Could not open application"),
                _("Could not open %s. It may not be installed.") % self.label,
            )
            return
        # Brief feedback; the app itself avoids duplicate windows
        self._action_btn.set_sensitive(False)
        self._action_btn.set_label(_("Opening…"))
        GLib.timeout_add(1800, self._restore_open_button)

    def _restore_open_button(self) -> bool:
        self._update_action()
        return GLib.SOURCE_REMOVE

    def _add_to_panel(self) -> None:
        error = add_plasmoid_to_panel(self.entry.plasmoid)
        window = self.get_root()
        if error:
            show_alert(
                self,
                _("Could not add %s to the panel") % self.label,
                _("Right-click the panel, choose “Add Widgets…” and search for %s.")
                % self.label
                + f"\n\n{error}",
            )
            return
        self.info = AppInfo(
            AppStatus.INSTALLED, repository=self.info.repository, in_panel=True
        )
        self._update_action()
        if hasattr(window, "add_toast"):
            window.add_toast(_("%s was added to the panel.") % self.label)


class AppsPage(Gtk.Box):
    """Page listing BigLinux applications that can be installed."""

    def __init__(self, data: dict) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.entries = [AppEntry.from_dict(a) for a in data.get("actions", [])]
        self.cards: list[AppCard] = []
        self._refreshing = False

        self._banner = Adw.Banner(
            title=_("You are offline. Connect to the internet to install applications.")
        )
        self.append(self._banner)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)
        self.append(scroll)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        main.set_margin_top(28)
        main.set_margin_bottom(32)
        main.set_margin_start(32)
        main.set_margin_end(32)
        scroll.set_child(main)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        main.append(header)
        header.append(make_heading(_(data.get("title", "")), "page-title"))
        subtitle = data.get("subtitle", "")
        if subtitle:
            sub = Gtk.Label(label=_(subtitle))
            sub.set_halign(Gtk.Align.CENTER)
            sub.add_css_class("page-subtitle")
            sub.set_wrap(True)
            sub.set_max_width_chars(70)
            sub.set_justify(Gtk.Justification.CENTER)
            header.append(sub)

        for entry in self.entries:
            card = AppCard(entry)
            card.set_size_request(AppCard.WIDTH, -1)
            self.cards.append(card)
        # Two cards per line when there is room, one on narrow windows
        main.append(card_grid(self.cards, 2, 16))

        monitor = Gio.NetworkMonitor.get_default()
        monitor.connect("notify::network-available", self._on_network_changed)
        self._on_network_changed(monitor)
        self.refresh()

    def _on_network_changed(self, monitor: Gio.NetworkMonitor, *_args) -> None:
        self._banner.set_revealed(not monitor.get_network_available())

    def refresh(self) -> None:
        """Re-check every application in the background."""
        if self._refreshing:
            return
        self._refreshing = True

        def worker() -> None:
            try:
                infos = check_apps(self.entries)
            except Exception:  # noqa: BLE001 — never leave cards "checking"
                infos = {}
            GLib.idle_add(self._apply, infos)

        threading.Thread(target=worker, daemon=True).start()

    def _apply(self, infos: dict[str, AppInfo]) -> bool:
        self._refreshing = False
        for card in self.cards:
            info = infos.get(card.entry.label, AppInfo(AppStatus.UNAVAILABLE))
            card.apply_info(info)
        return GLib.SOURCE_REMOVE
