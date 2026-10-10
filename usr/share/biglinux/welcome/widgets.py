"""BigLinux Welcome — Custom widget components with Orca accessibility."""

from __future__ import annotations

import gettext
import math
import os
import platform
import shlex
import shutil
from collections.abc import Callable
from typing import ClassVar

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import cairo
from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from install_backend import InstallJob, JobState
from utils import APP_PATH, get_desktop, load_browser_icon, load_icon

_ = gettext.gettext


def animations_enabled() -> bool:
    """Respect the desktop's reduced-motion preference."""
    settings = Gtk.Settings.get_default()
    return settings is None or settings.get_property("gtk-enable-animations")


def make_heading(text: str, css_class: str, level: int = 1) -> Gtk.Label:
    """Create a label exposed to screen readers as a heading."""
    label = Gtk.Label(label=text, accessible_role=Gtk.AccessibleRole.HEADING)
    label.set_halign(Gtk.Align.CENTER)
    label.add_css_class(css_class)
    label.set_wrap(True)
    label.set_justify(Gtk.Justification.CENTER)
    label.update_property([Gtk.AccessibleProperty.LEVEL], [level])
    return label


def show_alert(
    parent: Gtk.Widget,
    heading: str,
    body: str,
    responses: list[tuple[str, str, Adw.ResponseAppearance]] | None = None,
    on_response: Callable[[str], None] | None = None,
) -> Adw.AlertDialog:
    """Present an Adw.AlertDialog. responses: [(id, label, appearance)]."""
    dialog = Adw.AlertDialog(heading=heading, body=body)
    responses = responses or [("ok", _("OK"), Adw.ResponseAppearance.DEFAULT)]
    for response_id, label, appearance in responses:
        dialog.add_response(response_id, label)
        dialog.set_response_appearance(response_id, appearance)
    dialog.set_default_response(responses[-1][0])
    dialog.set_close_response(responses[0][0])
    if on_response:
        dialog.connect("response", lambda _d, r: on_response(r))
    dialog.present(parent.get_root())
    return dialog


def card_grid(cards: list[Gtk.Widget], per_line: int, spacing: int) -> Adw.Clamp:
    """Grid with up to per_line cards per line, centered, wrapping on narrow
    windows with the last line centered too.

    The width limit comes from an Adw.Clamp rather than halign=CENTER, so the
    wrap box is always measured and allocated at the same width (otherwise
    its height is computed for the wrong number of lines)."""
    grid = Adw.WrapBox(
        child_spacing=spacing,
        line_spacing=spacing,
        align=0.5,
        justify=Adw.JustifyMode.NONE,
    )
    widest = 0
    for card in cards:
        # Cards keep their size; expanding children would stretch a line
        card.set_hexpand(False)
        grid.append(card)
        widest = max(widest, card.measure(Gtk.Orientation.HORIZONTAL, -1)[1])
    per_line = max(1, min(per_line, len(cards)))
    line_length = per_line * widest + (per_line - 1) * spacing

    clamp = Adw.Clamp(maximum_size=line_length, tightening_threshold=line_length)
    clamp.set_child(grid)
    return clamp


def launch_command(command: str, widget: Gtk.Widget) -> None:
    """Launch a command line detached, with startup notification and a
    Wayland activation token so the new window gets focus.

    Raises GLib.Error when the program cannot be started."""
    app_info = Gio.AppInfo.create_from_commandline(
        command, None, Gio.AppInfoCreateFlags.SUPPORTS_STARTUP_NOTIFICATION
    )
    context = widget.get_display().get_app_launch_context()
    # Detach the app's output from ours, so it never writes to a closed
    # terminal or keeps our pipes open after we exit
    devnull = os.open(os.devnull, os.O_RDWR)
    try:
        app_info.launch_uris_as_manager_with_fds(
            [],
            context,
            GLib.SpawnFlags.SEARCH_PATH,
            None,
            None,
            None,
            None,
            devnull,
            devnull,
            devnull,
        )
    finally:
        os.close(devnull)


def command_available(command: str) -> bool:
    """Check that the program of a command line exists."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    return bool(argv) and shutil.which(argv[0]) is not None


# ---------------------------------------------------------------------------
# AnimatedLogo
# ---------------------------------------------------------------------------
class AnimatedLogo(Gtk.DrawingArea):
    """Animated glow effect around logo using Cairo.

    Driven by the frame clock, so it only runs while visible, and static
    when the user disabled animations."""

    def __init__(self, logo_widget: Gtk.Widget) -> None:
        super().__init__(accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self.logo_widget = logo_widget
        self.time = 0.0
        self._last_frame_time: int | None = None
        self.particles: list[dict] = []

        for i in range(8):
            angle = (i / 8) * 2 * math.pi
            self.particles.append(
                {
                    "angle": angle,
                    "speed": 0.3 + (i % 3) * 0.1,
                    "radius": 75 + (i % 2) * 12,
                    "size": 3 + (i % 3),
                    "alpha": 0.3 + (i % 3) * 0.15,
                }
            )

        self.set_size_request(185, 185)
        self.set_draw_func(self._draw)
        self.timer_id: int | None = self.add_tick_callback(self._on_tick)

    def _on_tick(self, _widget: Gtk.Widget, clock: Gdk.FrameClock) -> bool:
        now = clock.get_frame_time()
        last, self._last_frame_time = self._last_frame_time, now
        if not animations_enabled() or last is None:
            return GLib.SOURCE_CONTINUE
        # Same speed as the original 50 ms timer, but at the display's rate
        step = min(now - last, 100_000) / 1_000_000
        self.time += step
        for p in self.particles:
            p["angle"] += p["speed"] * step
        self.queue_draw()
        return GLib.SOURCE_CONTINUE

    def _draw(
        self,
        _area: Gtk.DrawingArea,
        cr: cairo.Context,
        width: int,
        height: int,
    ) -> None:
        cx, cy = width / 2, height / 2

        r, g, b = 0.33, 0.56, 0.85
        accent = Adw.StyleManager.get_default().get_accent_color()
        if accent is not None:
            rgba = accent.to_rgba()
            r, g, b = rgba.red, rgba.green, rgba.blue

        glow_alpha = 0.08 + 0.04 * math.sin(self.time * 1.5)
        for radius in [60, 72, 85]:
            alpha = glow_alpha * (1 - (radius - 60) / 35)
            cr.set_source_rgba(r, g, b, alpha)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.set_line_width(2)
            cr.stroke()

        for p in self.particles:
            px = cx + math.cos(p["angle"]) * p["radius"]
            py = cy + math.sin(p["angle"]) * p["radius"]

            cr.set_source_rgba(r, g, b, p["alpha"] * 0.5)
            cr.arc(px, py, p["size"] + 2, 0, 2 * math.pi)
            cr.fill()

            cr.set_source_rgba(r, g, b, p["alpha"])
            cr.arc(px, py, p["size"], 0, 2 * math.pi)
            cr.fill()

    def stop(self) -> None:
        if self.timer_id:
            self.remove_tick_callback(self.timer_id)
            self.timer_id = None


# ---------------------------------------------------------------------------
# InfoCard
# ---------------------------------------------------------------------------
class InfoCard(Gtk.Box):
    """System information card with accessible key-value pairs."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("info-card")
        self.set_halign(Gtk.Align.CENTER)

        session = os.environ.get("XDG_SESSION_TYPE", "")
        desktop = get_desktop()
        infos = [
            (_("Kernel"), platform.release()),
            (_("Desktop"), _("Unknown") if desktop == "Unknown" else desktop),
            (_("Display"), session.title() if session else _("Unknown")),
        ]

        for key, value in infos:
            row = Gtk.Box(spacing=40)
            row.add_css_class("info-row")

            key_label = Gtk.Label(
                label=key.upper(),
                accessible_role=Gtk.AccessibleRole.PRESENTATION,
            )
            key_label.add_css_class("info-key")
            key_label.set_halign(Gtk.Align.START)
            key_label.set_hexpand(True)
            row.append(key_label)

            val_label = Gtk.Label(label=value)
            val_label.add_css_class("info-value")
            val_label.set_halign(Gtk.Align.END)
            val_label.set_selectable(True)
            # Accessibility: announce both key and value together
            val_label.update_property(
                [Gtk.AccessibleProperty.LABEL], [f"{key}: {value}"]
            )
            row.append(val_label)

            self.append(row)


# ---------------------------------------------------------------------------
# ActionCard
# ---------------------------------------------------------------------------
class ActionCard(Gtk.Button):
    """Clickable action card with accessible label and error feedback.

    Launchers with a ``package`` key offer to install a missing application
    through the shared installer (see install_flow.py)."""

    # Ignore repeated clicks while an application starts (avoids duplicates)
    LAUNCH_FEEDBACK_MS = 1800

    def __init__(self, action: dict) -> None:
        super().__init__()
        self.action = action
        self._launching = False

        label_text = _(action.get("label", ""))
        self.label_text = label_text

        self.add_css_class("flat")
        self.add_css_class("action-card")
        is_qrcode = "qrcode" in action.get("icon", "").lower()
        if is_qrcode:
            self.add_css_class("qrcode-card")

        self.set_tooltip_text(label_text)
        # Accessibility: give the button a readable name
        self.update_property([Gtk.AccessibleProperty.LABEL], [label_text])
        self.connect("clicked", self._on_click)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        self.set_child(content)

        overlay = Gtk.Overlay()
        overlay.set_halign(Gtk.Align.CENTER)
        content.append(overlay)

        icon_box = Gtk.Box()
        icon_box.add_css_class("action-icon-box")
        icon_box.set_halign(Gtk.Align.CENTER)
        overlay.set_child(icon_box)

        icon_name = action.get("icon", "")
        icon = load_icon(icon_name, 200 if is_qrcode else 64)
        icon.add_css_class("action-icon")
        # Accessibility: describe QR code images
        if is_qrcode:
            icon.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [_("QR code: %s") % label_text],
            )
        icon_box.append(icon)

        self._spinner = Adw.Spinner()
        self._spinner.set_size_request(32, 32)
        self._spinner.set_halign(Gtk.Align.CENTER)
        self._spinner.set_valign(Gtk.Align.CENTER)
        self._spinner.set_visible(False)
        overlay.add_overlay(self._spinner)

        label = Gtk.Label(label=label_text)
        label.add_css_class("action-label")
        label.set_max_width_chars(11)
        label.set_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        content.append(label)

    def _on_click(self, _btn: Gtk.Button) -> None:
        action_type = self.action.get("type", "")
        command = self.action.get("command", "")

        if action_type == "app":
            self.open_app()
        elif action_type == "url":
            launcher = Gtk.UriLauncher.new(command)
            launcher.launch(self.get_root(), None, None, None)
        elif action_type == "script":
            self._launch(shlex.quote(os.path.join(APP_PATH, command)))
        elif action_type == "next":
            win = self.get_root()
            if hasattr(win, "_on_next"):
                win._on_next(None)

    def open_app(self) -> None:
        command = self.action.get("command", "")
        if self._launching:
            return
        if not command_available(command):
            self._on_missing_app()
            return
        self._launch(command)

    def _launch(self, command: str) -> None:
        try:
            launch_command(command, self)
        except GLib.Error:
            self._on_missing_app()
            return
        self._set_launching(True)
        GLib.timeout_add(self.LAUNCH_FEEDBACK_MS, self._set_launching, False)

    def _set_launching(self, launching: bool) -> bool:
        self._launching = launching
        self._spinner.set_visible(launching)
        if launching:
            self.add_css_class("launching")
        else:
            self.remove_css_class("launching")
        self.update_state([Gtk.AccessibleState.BUSY], [launching])
        return GLib.SOURCE_REMOVE

    def _on_missing_app(self) -> None:
        package = self.action.get("package", "")
        if package:
            # Imported here to keep widgets importable without a display
            from install_flow import offer_missing_app_install

            offer_missing_app_install(
                self,
                label=self.label_text,
                package=package,
                icon=self.action.get("icon", ""),
                on_installed=self.open_app,
            )
            return
        show_alert(
            self,
            _("Could not open application"),
            _("Could not open %s. It may not be installed.") % self.label_text,
        )


# ---------------------------------------------------------------------------
# BrowserCard
# ---------------------------------------------------------------------------
class BrowserCard(Gtk.Button):
    """Browser selection card with accessible state announcements."""

    def __init__(self, browser: dict, on_select) -> None:
        super().__init__()
        self.browser = browser
        self.on_select = on_select
        self.selected = False
        self.installed = self._check_installed()
        # None = not checked yet; False = not in the configured repositories
        self.available: bool | None = None
        self.detected_desktop: str | None = None

        self.add_css_class("flat")
        self.add_css_class("browser-card")

        if not self.installed:
            self.add_css_class("dimmed")

        browser_label = browser.get("label", "")
        self.set_tooltip_text(browser_label)
        self._update_accessible_name()
        self.connect("clicked", self._on_click)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        self.set_child(content)

        overlay = Gtk.Overlay()
        overlay.set_halign(Gtk.Align.CENTER)
        content.append(overlay)

        icon_bg = Gtk.Box()
        icon_bg.add_css_class("browser-icon-bg")
        overlay.set_child(icon_bg)

        icon = load_browser_icon(self.icon_name, 56)
        icon.add_css_class("browser-icon")
        icon_bg.append(icon)

        self.check_badge = Gtk.Box()
        self.check_badge.add_css_class("check-badge")
        self.check_badge.set_halign(Gtk.Align.END)
        self.check_badge.set_valign(Gtk.Align.END)
        self.check_badge.set_visible(False)

        check_icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
        check_icon.set_pixel_size(12)
        self.check_badge.append(check_icon)
        overlay.add_overlay(self.check_badge)

        self.spinner = Adw.Spinner()
        self.spinner.set_size_request(32, 32)
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_valign(Gtk.Align.CENTER)
        self.spinner.set_visible(False)
        overlay.add_overlay(self.spinner)

        label = Gtk.Label(label=browser_label)
        label.add_css_class("browser-label")
        label.set_max_width_chars(12)
        label.set_wrap(True)
        content.append(label)

    @property
    def icon_name(self) -> str:
        return self.browser.get("icon") or self.browser.get("package", "")

    def _check_installed(self) -> bool:
        for variant in self.browser.get("variants", []):
            check_path = variant.get("check", "")
            if check_path and os.path.exists(check_path):
                return True
        return False

    def _update_accessible_name(self) -> None:
        """Build a descriptive accessible name reflecting current state."""
        name = self.browser.get("label", "")
        parts = [name]
        if self.installed:
            parts.append(_("installed"))
        elif self.available is False:
            parts.append(_("unavailable"))
        else:
            parts.append(_("not installed"))
        if self.selected:
            parts.append(_("default browser"))
        self.update_property([Gtk.AccessibleProperty.LABEL], [", ".join(parts)])

    def set_installed(self, installed: bool) -> None:
        self.installed = installed
        if installed:
            self.remove_css_class("dimmed")
        else:
            self.add_css_class("dimmed")
        self._update_tooltip()
        self._update_accessible_name()

    def set_available(self, available: bool) -> None:
        self.available = available
        self._update_tooltip()
        self._update_accessible_name()

    def _update_tooltip(self) -> None:
        label = self.browser.get("label", "")
        if self.installed:
            self.set_tooltip_text(label)
        elif self.available is False:
            self.set_tooltip_text(
                _("%s is not available in the configured repositories") % label
            )
        else:
            self.set_tooltip_text(_("Install %s") % label)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        if selected:
            self.add_css_class("selected")
            self.check_badge.set_visible(True)
        else:
            self.remove_css_class("selected")
            self.check_badge.set_visible(False)
        self._update_accessible_name()

    def set_loading(self, loading: bool) -> None:
        self.spinner.set_visible(loading)
        if loading:
            self.add_css_class("dimmed")
        elif self.installed:
            self.remove_css_class("dimmed")
        # Accessibility: announce busy state to screen readers
        self.update_state([Gtk.AccessibleState.BUSY], [loading])

    def _on_click(self, _btn: Gtk.Button) -> None:
        self.on_select(self)


# ---------------------------------------------------------------------------
# ProgressDots
# ---------------------------------------------------------------------------
class ProgressDots(Gtk.Box):
    """Progress indicator with dots and accessible page announcement."""

    def __init__(self, total: int, page_titles: list[str] | None = None) -> None:
        super().__init__(spacing=8)
        self.add_css_class("progress-container")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)

        self.page_titles = page_titles or []
        self.dots: list[Gtk.Box] = []

        for i in range(total):
            dot = Gtk.Box(accessible_role=Gtk.AccessibleRole.PRESENTATION)
            dot.add_css_class("progress-dot")
            if i == 0:
                dot.add_css_class("active")
            title = self._get_title(i)
            if title:
                dot.set_tooltip_text(title)
            self.dots.append(dot)
            self.append(dot)

        # Accessibility: announce current position
        self._update_accessible_description(0)

    def _get_title(self, index: int) -> str:
        if index < len(self.page_titles):
            return self.page_titles[index]
        return ""

    def _update_accessible_description(self, page: int) -> None:
        total = len(self.dots)
        title = self._get_title(page)
        desc = f"{page + 1}/{total}"
        if title:
            desc = f"{title} — {desc}"
        self.update_property([Gtk.AccessibleProperty.LABEL], [desc])

    def set_page(self, page: int) -> None:
        for i, dot in enumerate(self.dots):
            dot.remove_css_class("active")
            dot.remove_css_class("completed")

            if i == page:
                dot.add_css_class("active")
            elif i < page:
                dot.add_css_class("completed")

        self._update_accessible_description(page)


# ---------------------------------------------------------------------------
# InstallPanel — Integrated installation view
# ---------------------------------------------------------------------------
class InstallPanel(Gtk.Box):
    """Installation view: progress bar, real-time log, cancel button,
    accessible status announcements and success/error end states.

    Bind it to an InstallJob with bind_job(); it can be attached at any time
    (the log so far is replayed), e.g. inside a "Details" dialog."""

    _TAG_COLORS: ClassVar[dict[str, tuple[str, str]]] = {
        # tag: (light theme, dark theme)
        "error": ("#c01c28", "#ff7b63"),
        "success": ("#1b8553", "#8ff0a4"),
        "warning": ("#9c6e03", "#f8e45c"),
        "info": ("#1c71d8", "#99c1f1"),
        "dim": ("#77767b", "#9a9996"),
    }

    def __init__(self, app_label: str, icon: str | None) -> None:
        """icon: image path relative to image/ (e.g. "browsers/firefox.svg")
        or an icon theme name."""
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.CENTER)
        self.set_vexpand(True)
        self.app_label = app_label
        self._pulse_id: int | None = None
        self._done_callback: Callable[[], None] | None = None
        self._cancel_callback: Callable[[], None] | None = None
        self._open_callback: Callable[[], None] | None = None
        self._cancelled = False
        self._job: InstallJob | None = None
        self._job_handlers: list[int] = []

        # -- Outer card --
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("install-panel")
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.set_size_request(420, -1)
        self.append(card)

        # -- Large centered icon --
        icon = load_icon(icon or "system-software-install-symbolic", 64)
        icon.set_halign(Gtk.Align.CENTER)
        card.append(icon)

        # -- Title (centered) --
        self._title = Gtk.Label(label=_("Installing %s…") % app_label)
        self._title.add_css_class("install-title")
        self._title.set_halign(Gtk.Align.CENTER)
        self._title.set_wrap(True)
        self._title.set_justify(Gtk.Justification.CENTER)
        card.append(self._title)

        # -- Subtitle / phase (centered) --
        self._subtitle = Gtk.Label(label=_("Preparing download…"))
        self._subtitle.add_css_class("install-subtitle")
        self._subtitle.set_halign(Gtk.Align.CENTER)
        self._subtitle.set_wrap(True)
        self._subtitle.set_justify(Gtk.Justification.CENTER)
        self._subtitle.set_max_width_chars(50)
        card.append(self._subtitle)

        # -- Progress bar with percentage --
        progress_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        progress_row.set_valign(Gtk.Align.CENTER)
        progress_row.set_margin_start(16)
        progress_row.set_margin_end(16)
        card.append(progress_row)

        self._progress = Gtk.ProgressBar()
        self._progress.add_css_class("install-progress")
        self._progress.set_show_text(False)
        self._progress.set_hexpand(True)
        self._progress.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Installation progress")]
        )
        progress_row.append(self._progress)

        self._percent_label = Gtk.Label(label="0%")
        self._percent_label.add_css_class("install-subtitle")
        self._percent_label.add_css_class("numeric")
        self._percent_label.set_width_chars(4)
        self._percent_label.set_xalign(1.0)
        progress_row.append(self._percent_label)

        # -- Log viewer (hidden by default, expandable) --
        self._toggle_btn = Gtk.ToggleButton(label=_("View details"))
        self._toggle_btn.set_active(False)
        self._toggle_btn.add_css_class("flat")
        self._toggle_btn.add_css_class("install-detail-toggle")
        self._toggle_btn.set_halign(Gtk.Align.CENTER)
        self._toggle_btn.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Show installation details")],
        )
        card.append(self._toggle_btn)

        self._revealer = Gtk.Revealer()
        self._revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
        self._revealer.set_transition_duration(250)
        self._revealer.set_reveal_child(False)
        card.append(self._revealer)

        log_frame = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        log_frame.add_css_class("install-log-frame")
        self._revealer.set_child(log_frame)

        log_scroll = Gtk.ScrolledWindow()
        log_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        log_scroll.set_min_content_height(160)
        log_scroll.set_max_content_height(280)
        log_frame.append(log_scroll)

        self._log_view = Gtk.TextView()
        self._log_view.set_editable(False)
        self._log_view.set_cursor_visible(False)
        self._log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self._log_view.add_css_class("install-log")
        self._log_view.set_monospace(True)
        self._log_view.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Installation log output")],
        )
        log_scroll.set_child(self._log_view)
        self._log_buffer = self._log_view.get_buffer()

        # Color tags for log lines, readable in light and dark themes
        for tag_name in self._TAG_COLORS:
            self._log_buffer.create_tag(tag_name)
        style_manager = Adw.StyleManager.get_default()
        self._apply_tag_colors(style_manager)
        self._dark_handler = style_manager.connect(
            "notify::dark", self._apply_tag_colors
        )

        self._toggle_btn.connect("toggled", self._on_toggle_details)

        # -- Action buttons --
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_row.set_halign(Gtk.Align.CENTER)
        card.append(btn_row)

        self._cancel_btn = Gtk.Button(label=_("Cancel"))
        self._cancel_btn.add_css_class("destructive-action")
        self._cancel_btn.add_css_class("pill")
        self._cancel_btn.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Cancel installation")],
        )
        self._cancel_btn.connect("clicked", self._on_cancel)
        btn_row.append(self._cancel_btn)

        self._open_btn = Gtk.Button(label=_("Open"))
        self._open_btn.add_css_class("pill")
        self._open_btn.set_visible(False)
        self._open_btn.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Open %s") % app_label]
        )
        self._open_btn.connect("clicked", self._on_open)
        btn_row.append(self._open_btn)

        self._done_btn = Gtk.Button(label=_("Done"))
        self._done_btn.add_css_class("install-done-button")
        self._done_btn.set_visible(False)
        self._done_btn.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Close installation panel")],
        )
        self._done_btn.connect("clicked", self._on_done)
        btn_row.append(self._done_btn)

        # Accessibility: live region
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Installing %s") % app_label],
        )

    def _apply_tag_colors(self, style_manager: Adw.StyleManager, *_args) -> None:
        dark = style_manager.get_dark()
        table = self._log_buffer.get_tag_table()
        for tag_name, (light_color, dark_color) in self._TAG_COLORS.items():
            table.lookup(tag_name).set_property(
                "foreground", dark_color if dark else light_color
            )

    # -- Job binding --

    def bind_job(self, job: InstallJob) -> None:
        """Follow a job's output, progress and result."""
        self.unbind_job()
        self._job = job
        for line in job.log_lines:
            self.append_log(line)
        if job.phase:
            self.set_progress(job.fraction, job.phase)
        else:
            self.start_pulse()
        self._cancel_btn.set_sensitive(job.cancellable and not job.cancel_requested)
        self._job_handlers = [
            job.connect("log", lambda _j, line: self.append_log(line)),
            job.connect("progress", lambda _j, f, p: self.set_progress(f, p)),
            job.connect("cancellable-changed", self._on_cancellable_changed),
            job.connect("finished", self._on_job_finished),
        ]
        self.set_cancel_callback(job.cancel)
        if not job.running and job.state is not JobState.PENDING:
            self._on_job_finished(job)

    def unbind_job(self) -> None:
        if self._job is not None:
            for handler in self._job_handlers:
                self._job.disconnect(handler)
        self._job = None
        self._job_handlers = []

    def _on_cancellable_changed(self, _job: InstallJob, cancellable: bool) -> None:
        if not cancellable and not self._cancelled:
            self._cancel_btn.set_sensitive(False)
            self._cancel_btn.set_tooltip_text(_("Cannot cancel during installation"))

    def _on_job_finished(self, job: InstallJob) -> None:
        if job.state is JobState.SUCCEEDED:
            self.set_success(self.app_label)
        elif job.state in (JobState.CANCELLED, JobState.AUTH_CANCELLED):
            self.set_cancelled(job.state is JobState.AUTH_CANCELLED)
        else:
            self.set_error(self.app_label, job.failure_text())

    # -- Public API --

    def start_pulse(self) -> None:
        """Start the progress bar pulse animation."""
        if self._pulse_id is None and animations_enabled():
            self._pulse_id = GLib.timeout_add(80, self._do_pulse)

    def stop_pulse(self) -> None:
        if self._pulse_id is not None:
            GLib.source_remove(self._pulse_id)
            self._pulse_id = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def append_log(self, line: str) -> None:
        """Append a line to the log viewer and auto-scroll."""
        end_iter = self._log_buffer.get_end_iter()
        tag_name = self._get_line_tag(line)
        if tag_name:
            tag = self._log_buffer.get_tag_table().lookup(tag_name)
            self._log_buffer.insert_with_tags(end_iter, line + "\n", tag)
        else:
            self._log_buffer.insert(end_iter, line + "\n")
        end_mark = self._log_buffer.create_mark(
            None, self._log_buffer.get_end_iter(), False
        )
        self._log_view.scroll_mark_onscreen(end_mark)
        self._log_buffer.delete_mark(end_mark)

    @staticmethod
    def _get_line_tag(line: str) -> str | None:
        """Return a color tag name based on the line content."""
        lower = line.lower().strip()
        if "error" in lower or "failed" in lower:
            return "error"
        if "successfully" in lower or "done" in lower:
            return "success"
        if "warning" in lower:
            return "warning"
        if lower.startswith(("installing", "removing", "checking", "resolving", "::")):
            return "info"
        if lower.startswith(("package", "total", "optional")):
            return "dim"
        return None

    def set_progress(self, fraction: float, phase_text: str = "") -> None:
        """Set the progress bar to a specific fraction and update label."""
        self.stop_pulse()
        clamped = max(0.0, min(1.0, fraction))
        self._progress.set_fraction(clamped)
        self._percent_label.set_label(f"{int(clamped * 100)}%")
        if phase_text and not self._cancelled:
            self._subtitle.set_label(phase_text)
            # Announce progress to screen readers
            self.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [f"{phase_text} {int(clamped * 100)}%"],
            )

    def set_success(self, app_label: str, message: str | None = None) -> None:
        """Show success state."""
        self.stop_pulse()
        self.set_progress(1.0, message or _("The application is ready to use."))
        self._title.set_label(_("%s installed successfully!") % app_label)
        self._title.remove_css_class("install-title")
        self._title.add_css_class("install-status-success")
        self._cancel_btn.set_visible(False)
        self._open_btn.set_visible(self._open_callback is not None)
        self._done_btn.set_visible(True)
        self._done_btn.grab_focus()
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("%s installed successfully") % app_label],
        )

    def set_error(self, app_label: str, message: str | None = None) -> None:
        """Show error state."""
        self.stop_pulse()
        self._progress.set_visible(False)
        self._percent_label.set_visible(False)
        self._title.set_label(_("Failed to install %s") % app_label)
        self._title.remove_css_class("install-title")
        self._title.add_css_class("install-status-error")
        self._subtitle.set_label(
            message or _("Check the details below for more information.")
        )
        self._toggle_btn.set_active(True)
        self._cancel_btn.set_visible(False)
        self._done_btn.set_visible(True)
        self._done_btn.grab_focus()
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Installation of %s failed") % app_label],
        )

    def set_cancelled(self, auth: bool = False) -> None:
        """Show the cancelled state (nothing was installed)."""
        self.stop_pulse()
        self._progress.set_visible(False)
        self._percent_label.set_visible(False)
        self._title.set_label(_("Installation cancelled"))
        self._subtitle.set_label(
            _("Authentication was cancelled. Nothing was installed.")
            if auth
            else _("Nothing was installed.")
        )
        self._cancel_btn.set_visible(False)
        self._done_btn.set_visible(True)
        self._done_btn.grab_focus()
        self.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Installation cancelled")]
        )

    def set_done_callback(self, callback: Callable[[], None]) -> None:
        self._done_callback = callback

    def set_cancel_callback(self, callback: Callable[[], None]) -> None:
        self._cancel_callback = callback

    def set_open_callback(self, callback: Callable[[], None] | None) -> None:
        self._open_callback = callback

    # -- Internal --

    def _do_pulse(self) -> bool:
        self._progress.pulse()
        return GLib.SOURCE_CONTINUE

    def _on_toggle_details(self, btn: Gtk.ToggleButton) -> None:
        revealed = btn.get_active()
        self._revealer.set_reveal_child(revealed)
        btn.set_label(_("Hide details") if revealed else _("View details"))
        btn.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [
                _("Hide installation details")
                if revealed
                else _("Show installation details")
            ],
        )

    def _on_cancel(self, _btn: Gtk.Button) -> None:
        self._cancelled = True
        self._cancel_btn.set_sensitive(False)
        self._cancel_btn.set_label(_("Cancelling…"))
        self._subtitle.set_label(_("Cancelling installation…"))
        if self._cancel_callback:
            self._cancel_callback()

    def _on_open(self, _btn: Gtk.Button) -> None:
        if self._open_callback:
            self._open_callback()
        self._on_done(_btn)

    def release(self) -> None:
        """Stop following the job and theme; call when the panel goes away."""
        self.stop_pulse()
        self.unbind_job()
        if self._dark_handler:
            Adw.StyleManager.get_default().disconnect(self._dark_handler)
            self._dark_handler = 0

    def _on_done(self, _btn: Gtk.Button) -> None:
        self.release()
        if self._done_callback:
            self._done_callback()
