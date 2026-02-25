"""BigLinux Welcome — Custom widget components with Orca accessibility."""

from __future__ import annotations

import gettext
import math
import os
import re
import shlex
import subprocess
from collections.abc import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GdkPixbuf", "2.0")

import cairo  # noqa: E402
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

from utils import APP_PATH, load_browser_icon, load_icon  # noqa: E402

_ = gettext.gettext


# ---------------------------------------------------------------------------
# AnimatedLogo
# ---------------------------------------------------------------------------
class AnimatedLogo(Gtk.DrawingArea):
    """Animated glow effect around logo using Cairo."""

    def __init__(self, logo_widget: Gtk.Widget) -> None:
        super().__init__(accessible_role=Gtk.AccessibleRole.PRESENTATION)
        self.logo_widget = logo_widget
        self.time = 0.0
        self.particles: list[dict] = []

        for i in range(8):
            angle = (i / 8) * 2 * math.pi
            self.particles.append({
                "angle": angle,
                "speed": 0.3 + (i % 3) * 0.1,
                "radius": 75 + (i % 2) * 12,
                "size": 3 + (i % 3),
                "alpha": 0.3 + (i % 3) * 0.15,
            })

        self.set_size_request(185, 185)
        self.set_draw_func(self._draw)
        # Accessibility: hide decorative element from screen readers
        self.update_property(
            [Gtk.AccessibleProperty.LABEL], ["BigLinux animated logo background"]
        )
        self.timer_id = GLib.timeout_add(50, self._animate)
        self.connect("unrealize", lambda _w: self.stop())

    def _animate(self) -> bool:
        self.time += 0.05
        for p in self.particles:
            p["angle"] += p["speed"] * 0.05
        self.queue_draw()
        return True

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
            GLib.source_remove(self.timer_id)
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

        from utils import get_desktop  # noqa: E402

        infos = [
            (_("Kernel"), __import__("platform").release()),
            (_("Desktop"), get_desktop()),
            (
                _("Display"),
                os.environ.get("XDG_SESSION_TYPE", "Unknown").title(),
            ),
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
    """Clickable action card with accessible label and error feedback."""

    def __init__(self, action: dict) -> None:
        super().__init__()
        self.action = action

        label_text = _(action.get("label", ""))

        self.add_css_class("flat")
        self.add_css_class("action-card")
        if "qrcode" in action.get("icon", "").lower():
            self.add_css_class("qrcode-card")

        self.set_tooltip_text(label_text)
        # Accessibility: give the button a readable name
        self.update_property([Gtk.AccessibleProperty.LABEL], [label_text])
        self.connect("clicked", self._on_click)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        self.set_child(content)

        icon_box = Gtk.Box()
        icon_box.add_css_class("action-icon-box")
        icon_box.set_halign(Gtk.Align.CENTER)
        content.append(icon_box)

        icon_name = action.get("icon", "")
        icon_size = 200 if "qrcode" in icon_name.lower() else 64
        icon = load_icon(icon_name, icon_size)
        icon.add_css_class("action-icon")
        # Accessibility: describe QR code images
        if "qrcode" in icon_name.lower():
            icon.update_property(
                [Gtk.AccessibleProperty.LABEL],
                [f"QR code: {label_text}"],
            )
        icon_box.append(icon)

        label = Gtk.Label(label=label_text)
        label.add_css_class("action-label")
        label.set_max_width_chars(11)
        label.set_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        content.append(label)

    def _on_click(self, _btn: Gtk.Button) -> None:
        action_type = self.action.get("type", "")
        command = self.action.get("command", "")

        try:
            if action_type == "app":
                subprocess.Popen(
                    shlex.split(command),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            elif action_type == "url":
                Gtk.show_uri(None, command, Gdk.CURRENT_TIME)
            elif action_type == "script":
                script = os.path.join(APP_PATH, command)
                subprocess.Popen(
                    shlex.split(script),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except OSError:
            label_text = _(self.action.get("label", ""))
            self._show_error(
                _("Could not open %s. It may not be installed.") % label_text
            )

    def _show_error(self, message: str) -> None:
        """Show an error dialog when an action fails."""
        win = self.get_root()
        if not isinstance(win, Gtk.Window):
            return
        dialog = Adw.AlertDialog(
            heading=_("Could not open application"),
            body=message,
        )
        dialog.add_response("ok", _("OK"))
        dialog.set_default_response("ok")
        dialog.present(win)


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

        icon = load_browser_icon(browser.get("package", ""), 56)
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

        self.spinner = Gtk.Spinner(spinning=False)
        self.spinner.set_halign(Gtk.Align.CENTER)
        self.spinner.set_valign(Gtk.Align.CENTER)
        self.spinner.set_visible(False)
        overlay.add_overlay(self.spinner)

        label = Gtk.Label(label=browser_label)
        label.add_css_class("browser-label")
        label.set_max_width_chars(12)
        label.set_wrap(True)
        content.append(label)

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
        self._update_accessible_name()

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
            self.spinner.start()
            self.add_css_class("dimmed")
        else:
            self.spinner.stop()
            if self.installed:
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
# InstallPanel — Integrated browser installation view
# ---------------------------------------------------------------------------
class InstallPanel(Gtk.Box):
    """Inline panel that replaces the browser grid while a browser is being installed.

    Features a progress bar with real percentage, real-time log viewer,
    cancel button, accessible status announcements, and success/error end-states.
    """

    # Milestone-based progress: keyword → fraction
    # Keywords must match actual pacman piped output (no progress bars, no %)
    _MILESTONES = [
        ("synchronizing", 0.05),
        ("resolving dependencies", 0.10),
        ("looking for conflicting", 0.15),
        ("retrieving", 0.20),
        ("checking key", 0.55),
        ("checking package integrity", 0.60),
        ("loading package", 0.65),
        ("checking for file conflicts", 0.70),
        ("checking available disk space", 0.75),
        ("processing package changes", 0.80),
        ("installing", 0.85),
        ("upgrading", 0.85),
        ("running post-transaction hooks", 0.95),
    ]

    def __init__(self, browser_label: str, browser_icon_path: str | None) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.CENTER)
        self.set_vexpand(True)
        self._pulse_id: int | None = None
        self._done_callback: Callable[[], None] | None = None
        self._cancel_callback: Callable[[], None] | None = None
        self._last_milestone = 0.0
        self._cancelled = False

        # -- Outer card --
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class("install-panel")
        card.set_halign(Gtk.Align.CENTER)
        card.set_valign(Gtk.Align.CENTER)
        card.set_size_request(480, -1)
        self.append(card)

        # -- Large centered icon --
        icon_size = 64
        if browser_icon_path and os.path.exists(browser_icon_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(
                    browser_icon_path, icon_size, icon_size
                )
                icon = Gtk.Image.new_from_pixbuf(pb)
            except GLib.Error:
                icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")
        else:
            icon = Gtk.Image.new_from_icon_name("web-browser-symbolic")

        icon.set_pixel_size(icon_size)
        icon.set_halign(Gtk.Align.CENTER)
        card.append(icon)

        # -- Title (centered) --
        self._title = Gtk.Label(label=_("Installing %s…") % browser_label)
        self._title.add_css_class("install-title")
        self._title.set_halign(Gtk.Align.CENTER)
        card.append(self._title)

        # -- Subtitle / phase (centered) --
        self._subtitle = Gtk.Label(label=_("Preparing download…"))
        self._subtitle.add_css_class("install-subtitle")
        self._subtitle.set_halign(Gtk.Align.CENTER)
        self._subtitle.set_wrap(True)
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
        progress_row.append(self._progress)

        self._percent_label = Gtk.Label(label="0%")
        self._percent_label.add_css_class("install-subtitle")
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

        # Color tags for log lines
        self._log_buffer.create_tag("error", foreground="#f66151")
        self._log_buffer.create_tag("success", foreground="#57e389")
        self._log_buffer.create_tag("warning", foreground="#f9f06b")
        self._log_buffer.create_tag("info", foreground="#99c1f1")
        self._log_buffer.create_tag("dim", foreground="#9a9996")

        self._toggle_btn.connect("toggled", self._on_toggle_details)

        # -- Action buttons --
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        btn_row.set_halign(Gtk.Align.CENTER)
        card.append(btn_row)

        self._cancel_btn = Gtk.Button(label=_("Cancel"))
        self._cancel_btn.add_css_class("destructive-action")
        self._cancel_btn.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Cancel installation")],
        )
        self._cancel_btn.connect("clicked", self._on_cancel)
        btn_row.append(self._cancel_btn)

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
            [_("Installing %s") % browser_label],
        )

    # -- Public API --

    def start_pulse(self) -> None:
        """Start the progress bar pulse animation."""
        if self._pulse_id is None:
            self._pulse_id = GLib.timeout_add(80, self._do_pulse)

    def stop_pulse(self) -> None:
        if self._pulse_id is not None:
            GLib.source_remove(self._pulse_id)
            self._pulse_id = None

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def append_log(self, line: str) -> None:
        """Append a line to the log viewer, auto-scroll, and parse progress."""
        end_iter = self._log_buffer.get_end_iter()
        tag_name = self._get_line_tag(line)
        if tag_name:
            tag = self._log_buffer.get_tag_table().lookup(tag_name)
            self._log_buffer.insert_with_tags(end_iter, line + "\n", tag)
        else:
            self._log_buffer.insert(end_iter, line + "\n")
        # Auto-scroll
        end_mark = self._log_buffer.create_mark(
            None, self._log_buffer.get_end_iter(), False
        )
        self._log_view.scroll_mark_onscreen(end_mark)
        self._log_buffer.delete_mark(end_mark)
        # Parse progress
        self._parse_progress(line)

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

    def parse_progress(self, line: str) -> None:
        """Public interface: parse progress without adding to log."""
        self._parse_progress(line)

    def set_progress(self, fraction: float, phase_text: str = "") -> None:
        """Set the progress bar to a specific fraction and update label."""
        self.stop_pulse()
        clamped = max(0.0, min(1.0, fraction))
        self._progress.set_fraction(clamped)
        self._percent_label.set_label(f"{int(clamped * 100)}%")
        if phase_text:
            self._subtitle.set_label(phase_text)

    def set_success(self, browser_label: str) -> None:
        """Show success state."""
        self.stop_pulse()
        self.set_progress(1.0, _("It has been set as your default browser."))
        self._title.set_label(_("%s installed successfully!") % browser_label)
        self._title.remove_css_class("install-title")
        self._title.add_css_class("install-status-success")
        self._cancel_btn.set_visible(False)
        self._done_btn.set_visible(True)
        self._done_btn.grab_focus()
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("%s installed successfully") % browser_label],
        )

    def set_error(self, browser_label: str) -> None:
        """Show error state."""
        self.stop_pulse()
        self._progress.set_visible(False)
        self._percent_label.set_visible(False)
        self._title.set_label(_("Failed to install %s") % browser_label)
        self._title.remove_css_class("install-title")
        self._title.add_css_class("install-status-error")
        self._subtitle.set_label(_("Check the details below for more information."))
        self._revealer.set_reveal_child(True)
        self._cancel_btn.set_visible(False)
        self._done_btn.set_visible(True)
        self._done_btn.grab_focus()
        self.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Installation of %s failed") % browser_label],
        )

    def set_done_callback(self, callback: Callable[[], None]) -> None:
        self._done_callback = callback

    def set_cancel_callback(self, callback: Callable[[], None]) -> None:
        self._cancel_callback = callback

    # -- Internal --

    # Use untranslated strings at class level; translate at lookup time
    _PHASE_LABELS = {
        "synchronizing": "Synchronizing databases…",
        "resolving dependencies": "Resolving dependencies…",
        "looking for conflicting": "Checking for conflicts…",
        "retrieving": "Downloading packages…",
        "checking key": "Verifying signatures…",
        "checking package integrity": "Verifying integrity…",
        "loading package": "Loading packages…",
        "checking for file conflicts": "Checking for conflicts…",
        "checking available disk space": "Checking disk space…",
        "processing package changes": "Applying changes…",
        "installing": "Installing…",
        "upgrading": "Upgrading…",
        "running post-transaction hooks": "Running post-install hooks…",
    }

    # Cancel is disabled once filesystem changes begin
    _CANCEL_CUTOFF = 0.80  # "processing package changes"

    # Regex for download progress lines:
    # " firefox-138.0.4-1  45.2 MiB  12.5 MiB/s 00:03 [###] 58%"
    _RE_DOWNLOAD = re.compile(r"(\d+(?:\.\d+)?\s*[KMG]iB/s).*?(\d{1,3})%")

    def _parse_progress(self, line: str) -> None:
        """Parse pacman/yay output using milestone keywords."""
        lower = line.lower()

        # Check milestone keywords first
        matched_milestone = False
        for keyword, fraction in self._MILESTONES:
            if keyword in lower and fraction > self._last_milestone:
                self._last_milestone = fraction
                self.stop_pulse()
                self._progress.set_fraction(fraction)
                self._percent_label.set_label(f"{int(fraction * 100)}%")
                label = self._PHASE_LABELS.get(keyword, "")
                if label:
                    self._subtitle.set_label(_(label))
                    # Announce progress to screen readers at each milestone
                    pct = int(fraction * 100)
                    self.update_property(
                        [Gtk.AccessibleProperty.LABEL],
                        [f"{_(label)} {pct}%"],
                    )
                matched_milestone = True

                # Disable cancel once real installation begins
                if fraction >= self._CANCEL_CUTOFF:
                    self._cancel_btn.set_sensitive(False)
                    self._cancel_btn.set_tooltip_text(
                        _("Cannot cancel during installation")
                    )

                break

        # During download phase, update subtitle with package name or speed info
        if not matched_milestone and 0.05 <= self._last_milestone < 0.55:
            # Show what's being downloaded (piped output: "chromium ... downloading...")
            if "downloading" in lower:
                name = line.strip().replace("downloading...", "").strip()
                if name:
                    self._subtitle.set_label(_("Downloading {name}…").format(name=name))
            # If terminal-mode output with speed (rare for piped pacman)
            else:
                dl_match = self._RE_DOWNLOAD.search(line)
                if dl_match:
                    speed = dl_match.group(1)
                    pct = int(dl_match.group(2))
                    fraction = 0.20 + (pct / 100.0) * 0.35
                    self.stop_pulse()
                    self._progress.set_fraction(fraction)
                    self._percent_label.set_label(f"{int(fraction * 100)}%")
                    self._subtitle.set_label(
                        _("Downloading… {pct}% ({speed})").format(pct=pct, speed=speed)
                    )

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

    def _on_done(self, _btn: Gtk.Button) -> None:
        self.stop_pulse()
        if self._done_callback:
            self._done_callback()
