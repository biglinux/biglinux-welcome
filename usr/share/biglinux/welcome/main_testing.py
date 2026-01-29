#!/usr/bin/env python3
"""BigLinux Welcome - Final Award-Winning Design.

Clean, performant implementation using:
- Cairo animation for elegant logo effects
- Proper icon loading for browsers and actions
- Adwaita-native colors with subtle glassmorphism
- Responsive and accessible UI
"""

from __future__ import annotations

import gettext
import locale
import math
import os
import platform
import shlex
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import cairo  # noqa: E402
import yaml  # noqa: E402
from gi.repository import Adw, Gdk, GdkPixbuf, GLib, Gtk  # noqa: E402

# Internationalization
DOMAIN = "biglinux-welcome"
LOCALE_DIR = "/usr/share/locale"
locale.setlocale(locale.LC_ALL, "")
locale.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.textdomain(DOMAIN)
_ = gettext.gettext

APP_PATH = os.path.dirname(os.path.abspath(__file__))

# Premium CSS with elegant animations
PREMIUM_CSS = """
/* Base window with subtle gradient feel */
window.background {
    background: @window_bg_color;
}

headerbar.flat {
    background: transparent;
    border: none;
    box-shadow: none;
}

.logo-container {
    padding: 20px;
    min-width: 180px;
    min-height: 180px;
}

.logo-image {
    min-width: 130px;
    min-height: 130px;
}

.hero-title {
    font-size: 36px;
    font-weight: 900;
    letter-spacing: -1.2px;
}

.hero-subtitle {
    font-size: 15px;
    font-weight: 400;
    opacity: 0.55;
    letter-spacing: 0.2px;
}

.hero-version {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    padding: 6px 16px;
    border-radius: 100px;
    background: alpha(@accent_bg_color, 0.12);
    color: @accent_color;
}

/* System Info Card - Refined glassmorphism with subtle shine */
.info-card {
    background: alpha(@card_bg_color, 0.55);
    border-radius: 16px;
    padding: 14px 28px;
    border: 1px solid alpha(@borders, 0.06);
    border-top: 1px solid alpha(white, 0.1);
    box-shadow: 0 4px 20px alpha(black, 0.03),
                0 1px 3px alpha(black, 0.02);
}

.info-row { padding: 5px 0; }
.info-key { font-size: 10px; font-weight: 700; opacity: 0.4; letter-spacing: 1px; text-transform: uppercase; }
.info-value { font-size: 13px; font-weight: 500; }

/* Page Headers - Strong typography */
.page-title { 
    font-size: 32px; 
    font-weight: 900; 
    letter-spacing: -0.8px;
}

.page-subtitle { 
    font-size: 15px; 
    opacity: 0.5; 
    letter-spacing: 0.1px;
    line-height: 1.5;
}

/* Action Cards - Modern elevated style with subtle shine */
.action-card {
    background: alpha(@card_bg_color, 0.5);
    border-radius: 18px;
    border: 1px solid alpha(@borders, 0.06);
    border-top: 1px solid alpha(white, 0.08);
    padding: 18px 14px;
    min-width: 125px;
    min-height: 120px;
    box-shadow: 0 2px 12px alpha(black, 0.02), 
                0 1px 3px alpha(black, 0.03);
}

.action-card:hover {
    background: alpha(@card_bg_color, 0.85);
    border: 1px solid alpha(@accent_bg_color, 0.15);
    border-top: 1px solid alpha(white, 0.15);
    box-shadow: 0 8px 32px alpha(black, 0.06),
                0 2px 8px alpha(black, 0.04);
}

.action-icon {
    min-width: 52px;
    min-height: 52px;
}

.action-icon-box {
    background: transparent;
    border-radius: 14px;
    padding: 8px;
}

.action-label { 
    font-size: 12px; 
    font-weight: 700;
    opacity: 0.85;
    letter-spacing: 0.1px;
}

/* QR Code special styling */
.qrcode-card {
    min-width: 240px;
    min-height: 280px;
    background: alpha(@card_bg_color, 0.7);
    border-radius: 24px;
}

.qrcode-card .action-icon-box {
    background: white;
    border-radius: 16px;
    padding: 12px;
}

/* Browser Cards - Premium selection UI with subtle shine */
.browser-card {
    background: alpha(@card_bg_color, 0.5);
    border-radius: 20px;
    border: 2px solid transparent;
    border-top: 1px solid alpha(white, 0.08);
    padding: 18px 16px;
    min-width: 130px;
    min-height: 135px;
    box-shadow: 0 2px 12px alpha(black, 0.02),
                0 1px 3px alpha(black, 0.03);
}

.browser-card:hover {
    background: alpha(@card_bg_color, 0.85);
    border: 2px solid alpha(@accent_bg_color, 0.15);
    border-top: 1px solid alpha(white, 0.15);
    box-shadow: 0 8px 32px alpha(black, 0.06),
                0 2px 8px alpha(black, 0.04);
}

.browser-card.selected {
    background: alpha(@accent_bg_color, 0.1);
    border: 2px solid @accent_bg_color;
    border-top: 2px solid mix(@accent_bg_color, white, 0.7);
    box-shadow: 0 4px 24px alpha(@accent_bg_color, 0.2),
                0 0 0 1px alpha(@accent_bg_color, 0.1);
}

.browser-card.dimmed { opacity: 0.45; }
.browser-card.dimmed:hover { opacity: 0.65; }

.browser-icon {
    min-width: 60px;
    min-height: 60px;
}

.browser-icon-bg {
    background: transparent;
    border-radius: 16px;
    padding: 6px;
}

.browser-label { 
    font-size: 12px; 
    font-weight: 700;
    opacity: 0.85;
}

.check-badge {
    background: @success_bg_color;
    border-radius: 50%;
    padding: 4px;
    box-shadow: 0 2px 8px alpha(@success_bg_color, 0.3);
}

/* Progress Indicator - iOS-inspired pills */
.progress-container { padding: 6px 0; }

.progress-dot {
    min-width: 10px;
    min-height: 10px;
    border-radius: 50%;
    background: alpha(@theme_fg_color, 0.12);
}

.progress-dot.active {
    min-width: 32px;
    border-radius: 100px;
    background: @accent_bg_color;
    box-shadow: 0 2px 8px alpha(@accent_bg_color, 0.3);
}

.progress-dot.completed {
    background: alpha(@accent_bg_color, 0.4);
}

/* Navigation Buttons - Minimal and elegant */
.nav-button {
    min-width: 44px;
    min-height: 44px;
    border-radius: 50%;
}

.nav-button.back {
    background: alpha(@theme_fg_color, 0.05);
    color: alpha(@theme_fg_color, 0.6);
}

.nav-button.back:hover {
    background: alpha(@theme_fg_color, 0.1);
    color: alpha(@theme_fg_color, 0.8);
}

.nav-button.next {
    background: @accent_bg_color;
    color: white;
    box-shadow: 0 4px 16px alpha(@accent_bg_color, 0.3);
}

.nav-button.next:hover {
    box-shadow: 0 6px 20px alpha(@accent_bg_color, 0.4);
}

.finish-button {
    padding: 12px 32px;
    border-radius: 100px;
    font-weight: 700;
    font-size: 14px;
    letter-spacing: 0.3px;
    background: @accent_bg_color;
    color: white;
    box-shadow: 0 4px 16px alpha(@accent_bg_color, 0.3);
}

.finish-button:hover {
    box-shadow: 0 6px 24px alpha(@accent_bg_color, 0.4);
}

/* Bottom Bar */
.bottom-bar { padding: 14px 28px 22px 28px; }
.startup-check { font-size: 13px; opacity: 0.5; font-weight: 500; }

/* Placeholder classes for animations */
.animate-1 { }
.animate-2 { }
.animate-3 { }
.animate-4 { }
"""


def load_icon(name: str, size: int = 64) -> Gtk.Image:
    """Load icon from various sources."""
    img = None

    # Check if it's a local file (svg/png)
    if name.endswith((".svg", ".png")):
        path = os.path.join(APP_PATH, "image", name)
        if os.path.exists(path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
                img = Gtk.Image.new_from_pixbuf(pb)
            except GLib.Error:
                pass

    # Try as theme icon
    if img is None:
        img = Gtk.Image.new_from_icon_name(name or "application-x-executable")

    # Always set pixel size
    img.set_pixel_size(size)
    return img


def load_browser_icon(package: str, size: int = 64) -> Gtk.Image:
    """Load browser icon from browsers folder."""
    path = os.path.join(APP_PATH, "image", "browsers", f"{package}.svg")
    img = None

    if os.path.exists(path):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
            img = Gtk.Image.new_from_pixbuf(pb)
        except GLib.Error:
            pass

    # Fallback to theme icon
    if img is None:
        img = Gtk.Image.new_from_icon_name("web-browser-symbolic")

    # Always set pixel size
    img.set_pixel_size(size)
    return img


class AnimatedLogo(Gtk.DrawingArea):
    """Animated glow effect around logo using Cairo."""

    def __init__(self, logo_widget: Gtk.Widget) -> None:
        super().__init__()
        self.logo_widget = logo_widget
        self.time = 0.0
        self.particles: list[dict] = []

        # Create 8 particles orbiting
        for i in range(8):
            angle = (i / 8) * 2 * math.pi
            self.particles.append({
                "angle": angle,
                "speed": 0.3 + (i % 3) * 0.1,  # Varied speeds
                "radius": 75 + (i % 2) * 12,  # Varied orbit radii
                "size": 3 + (i % 3),
                "alpha": 0.3 + (i % 3) * 0.15,
            })

        self.set_size_request(185, 185)
        self.set_draw_func(self._draw)

        # Start animation at ~20fps
        self.timer_id = GLib.timeout_add(50, self._animate)

    def _animate(self) -> bool:
        """Update animation state."""
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
        """Draw particles with Cairo."""
        cx, cy = width / 2, height / 2

        # Get accent color from Adwaita
        style = self.get_style_context()
        color = style.lookup_color("accent_bg_color")
        if color[0]:
            r, g, b = color[1].red, color[1].green, color[1].blue
        else:
            r, g, b = 0.33, 0.56, 0.85  # Blue fallback

        # Draw subtle glow ring (breathing effect)
        glow_alpha = 0.08 + 0.04 * math.sin(self.time * 1.5)
        for radius in [60, 72, 85]:
            alpha = glow_alpha * (1 - (radius - 60) / 35)
            cr.set_source_rgba(r, g, b, alpha)
            cr.arc(cx, cy, radius, 0, 2 * math.pi)
            cr.set_line_width(2)
            cr.stroke()

        # Draw orbiting particles
        for p in self.particles:
            px = cx + math.cos(p["angle"]) * p["radius"]
            py = cy + math.sin(p["angle"]) * p["radius"]

            # Particle with glow
            cr.set_source_rgba(r, g, b, p["alpha"] * 0.5)
            cr.arc(px, py, p["size"] + 2, 0, 2 * math.pi)
            cr.fill()

            cr.set_source_rgba(r, g, b, p["alpha"])
            cr.arc(px, py, p["size"], 0, 2 * math.pi)
            cr.fill()

    def stop(self) -> None:
        """Stop animation."""
        if self.timer_id:
            GLib.source_remove(self.timer_id)
            self.timer_id = None


class InfoCard(Gtk.Box):
    """System information card."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add_css_class("info-card")
        self.set_halign(Gtk.Align.CENTER)

        infos = [
            (_("Kernel"), platform.release()),
            (_("Desktop"), self._get_desktop()),
            (_("Display"), os.environ.get("XDG_SESSION_TYPE", "Unknown").title()),
        ]

        for key, value in infos:
            row = Gtk.Box(spacing=40)
            row.add_css_class("info-row")

            key_label = Gtk.Label(label=key.upper())
            key_label.add_css_class("info-key")
            key_label.set_halign(Gtk.Align.START)
            key_label.set_hexpand(True)
            row.append(key_label)

            val_label = Gtk.Label(label=value)
            val_label.add_css_class("info-value")
            val_label.set_halign(Gtk.Align.END)
            val_label.set_selectable(True)
            row.append(val_label)

            self.append(row)

    def _get_desktop(self) -> str:
        """Get desktop environment."""
        de = os.environ.get("XDG_CURRENT_DESKTOP", "")
        if "KDE" in de:
            return "Plasma"
        if "GNOME" in de:
            return "GNOME"
        return de or _("Unknown")


class ActionCard(Gtk.Button):
    """Action card widget."""

    def __init__(self, action: dict) -> None:
        super().__init__()
        self.action = action

        self.add_css_class("flat")
        self.add_css_class("action-card")
        # Larger card for QR codes
        if "qrcode" in action.get("icon", "").lower():
            self.add_css_class("qrcode-card")
        self.set_tooltip_text(_(action.get("label", "")))
        self.connect("clicked", self._on_click)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        self.set_child(content)

        # Icon box
        icon_box = Gtk.Box()
        icon_box.add_css_class("action-icon-box")
        icon_box.set_halign(Gtk.Align.CENTER)
        content.append(icon_box)

        # Icon - larger size for QR codes
        icon_name = action.get("icon", "")
        icon_size = 200 if "qrcode" in icon_name.lower() else 64
        icon = load_icon(icon_name, icon_size)
        icon.add_css_class("action-icon")
        icon_box.append(icon)

        # Label
        label = Gtk.Label(label=_(action.get("label", "")))
        label.add_css_class("action-label")
        label.set_max_width_chars(11)
        label.set_wrap(True)
        label.set_justify(Gtk.Justification.CENTER)
        content.append(label)

    def _on_click(self, _btn: Gtk.Button) -> None:
        """Handle click."""
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
        except OSError as e:
            print(f"Action error: {e}")


class BrowserCard(Gtk.Button):
    """Browser selection card."""

    def __init__(self, browser: dict, on_select) -> None:
        super().__init__()
        self.browser = browser
        self.on_select = on_select
        self.selected = False
        self.installed = self._check_installed()

        self.add_css_class("flat")
        self.add_css_class("browser-card")

        if not self.installed:
            self.add_css_class("dimmed")

        self.set_tooltip_text(browser.get("label", ""))
        self.connect("clicked", self._on_click)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content.set_halign(Gtk.Align.CENTER)
        content.set_valign(Gtk.Align.CENTER)
        content.set_margin_top(10)
        content.set_margin_bottom(10)
        self.set_child(content)

        # Icon with overlay for check badge
        overlay = Gtk.Overlay()
        overlay.set_halign(Gtk.Align.CENTER)
        content.append(overlay)

        # Icon background
        icon_bg = Gtk.Box()
        icon_bg.add_css_class("browser-icon-bg")
        overlay.set_child(icon_bg)

        # Icon
        icon = load_browser_icon(browser.get("package", ""), 56)
        icon.add_css_class("browser-icon")
        icon_bg.append(icon)

        # Check badge (initially hidden)
        self.check_badge = Gtk.Box()
        self.check_badge.add_css_class("check-badge")
        self.check_badge.set_halign(Gtk.Align.END)
        self.check_badge.set_valign(Gtk.Align.END)
        self.check_badge.set_visible(False)

        check_icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
        check_icon.set_pixel_size(12)
        self.check_badge.append(check_icon)
        overlay.add_overlay(self.check_badge)

        # Label
        label = Gtk.Label(label=browser.get("label", ""))
        label.add_css_class("browser-label")
        label.set_max_width_chars(12)
        label.set_wrap(True)
        content.append(label)

    def _check_installed(self) -> bool:
        """Check if browser is installed."""
        for variant in self.browser.get("variants", []):
            check_path = variant.get("check", "")
            if check_path and os.path.exists(check_path):
                return True
        return False

    def set_selected(self, selected: bool) -> None:
        """Set selection state."""
        self.selected = selected
        if selected:
            self.add_css_class("selected")
            self.check_badge.set_visible(True)
        else:
            self.remove_css_class("selected")
            self.check_badge.set_visible(False)

    def _on_click(self, _btn: Gtk.Button) -> None:
        """Handle click."""
        if self.installed:
            self.on_select(self)


class ProgressDots(Gtk.Box):
    """Progress indicator with dots."""

    def __init__(self, total: int) -> None:
        super().__init__(spacing=8)
        self.add_css_class("progress-container")
        self.set_halign(Gtk.Align.CENTER)
        self.set_valign(Gtk.Align.CENTER)

        self.dots: list[Gtk.Box] = []
        for i in range(total):
            dot = Gtk.Box()
            dot.add_css_class("progress-dot")
            if i == 0:
                dot.add_css_class("active")
            self.dots.append(dot)
            self.append(dot)

    def set_page(self, page: int) -> None:
        """Update active page."""
        for i, dot in enumerate(self.dots):
            dot.remove_css_class("active")
            dot.remove_css_class("completed")

            if i == page:
                dot.add_css_class("active")
            elif i < page:
                dot.add_css_class("completed")


class WelcomeWindow(Adw.ApplicationWindow):
    """Main welcome window."""

    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)
        self.set_default_size(1000, 740)
        # Keep empty title for cleaner look
        self.set_title("")

        self.pages_data = self._load_pages()
        self.current_page = 0
        self.page_widgets: list[Gtk.Widget] = []
        self.browser_cards: list[BrowserCard] = []

        self._build_ui()

    def _load_pages(self) -> list | None:
        """Load pages from YAML."""
        try:
            with open(os.path.join(APP_PATH, "pages.yaml"), encoding="utf-8") as f:
                return yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError):
            return None

    def _build_ui(self) -> None:
        """Build the UI."""
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main)

        # Header - minimal without title
        header = Adw.HeaderBar()
        header.add_css_class("flat")
        header.set_show_title(False)
        main.append(header)

        # Stack
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(320)
        self.stack.set_vexpand(True)
        main.append(self.stack)

        self._build_pages()
        self._build_nav(main)

    def _build_pages(self) -> None:
        """Build all pages."""
        # Welcome page
        welcome = self._build_welcome()
        self.stack.add_named(welcome, "welcome")
        self.page_widgets.append(welcome)

        # Content pages
        if self.pages_data:
            for i, data in enumerate(self.pages_data):
                if data.get("page_type") == "browsers":
                    page = self._build_browser_page(data)
                else:
                    page = self._build_action_page(data)
                self.stack.add_named(page, f"page_{i}")
                self.page_widgets.append(page)

    def _build_welcome(self) -> Gtk.Widget:
        """Build welcome page."""
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        main.set_valign(Gtk.Align.CENTER)
        main.set_halign(Gtk.Align.CENTER)
        main.set_margin_top(0)
        main.set_margin_bottom(8)
        scroll.set_child(main)

        os_info = self._parse_os_release()

        # Logo with animated glow effect
        logo_path = self._get_logo_path(os_info)
        if logo_path and os.path.exists(logo_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(logo_path, 130, 130)
                logo = Gtk.Image.new_from_pixbuf(pb)
            except GLib.Error:
                logo = Gtk.Image.new_from_icon_name("distributor-logo")
        else:
            logo = Gtk.Image.new_from_icon_name("distributor-logo")

        logo.set_pixel_size(130)
        logo.set_halign(Gtk.Align.CENTER)
        logo.set_valign(Gtk.Align.CENTER)
        logo.add_css_class("logo-image")

        # Create overlay with animated background
        logo_overlay = Gtk.Overlay()
        logo_overlay.set_halign(Gtk.Align.CENTER)

        # Animated Cairo background
        self.logo_animation = AnimatedLogo(logo)
        logo_overlay.set_child(self.logo_animation)

        # Logo on top
        logo_overlay.add_overlay(logo)

        main.append(logo_overlay)

        # Title
        distro = os_info.get("PRETTY_NAME", "BigLinux")
        title = Gtk.Label(label=distro)
        title.add_css_class("hero-title")
        title.add_css_class("animate-2")
        main.append(title)

        # Subtitle
        subtitle = Gtk.Label(label=_("Welcome to your new system"))
        subtitle.add_css_class("hero-subtitle")
        subtitle.add_css_class("animate-2")
        main.append(subtitle)

        # Version badge
        version = os_info.get("VERSION", "")
        if version:
            badge = Gtk.Label(label=f"v{version}")
            badge.add_css_class("hero-version")
            badge.add_css_class("animate-3")
            main.append(badge)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_size_request(-1, 10)
        main.append(spacer)

        # Info card
        info = InfoCard()
        info.add_css_class("animate-4")
        main.append(info)

        return scroll

    def _build_action_page(self, data: dict) -> Gtk.Widget:
        """Build action page."""
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        main.set_margin_top(28)
        main.set_margin_bottom(32)
        main.set_margin_start(40)
        main.set_margin_end(40)
        scroll.set_child(main)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header.set_halign(Gtk.Align.CENTER)
        main.append(header)

        title = Gtk.Label(label=_(data.get("title", "")))
        title.add_css_class("page-title")
        header.append(title)

        subtitle = data.get("subtitle", "")
        if subtitle:
            sub = Gtk.Label(label=_(subtitle))
            sub.add_css_class("page-subtitle")
            sub.set_wrap(True)
            sub.set_max_width_chars(60)
            sub.set_justify(Gtk.Justification.CENTER)
            header.append(sub)

        # Cards in manual rows for proper centering
        actions = data.get("actions", [])
        items_per_row = 4  # Max items per row
        cards_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        cards_container.set_halign(Gtk.Align.CENTER)
        main.append(cards_container)

        # Create rows
        for i in range(0, len(actions), items_per_row):
            row_actions = actions[i : i + items_per_row]
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            row.set_halign(Gtk.Align.CENTER)
            cards_container.append(row)

            for action in row_actions:
                card = ActionCard(action)
                row.append(card)

        return scroll

    def _build_browser_page(self, data: dict) -> Gtk.Widget:
        """Build browser selection page."""
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        main.set_margin_top(28)
        main.set_margin_bottom(32)
        main.set_margin_start(40)
        main.set_margin_end(40)
        scroll.set_child(main)

        # Header
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header.set_halign(Gtk.Align.CENTER)
        main.append(header)

        title = Gtk.Label(label=_(data.get("title", "")))
        title.add_css_class("page-title")
        header.append(title)

        subtitle = data.get("subtitle", "")
        if subtitle:
            sub = Gtk.Label(label=_(subtitle))
            sub.add_css_class("page-subtitle")
            sub.set_wrap(True)
            sub.set_max_width_chars(55)
            sub.set_justify(Gtk.Justification.CENTER)
            header.append(sub)

        # Browser cards in manual rows for proper centering
        browsers = data.get("actions", [])
        items_per_row = 5  # Max items per row
        cards_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        cards_container.set_halign(Gtk.Align.CENTER)
        main.append(cards_container)

        self.browser_cards = []
        # Create rows
        for i in range(0, len(browsers), items_per_row):
            row_browsers = browsers[i : i + items_per_row]
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            row.set_halign(Gtk.Align.CENTER)
            cards_container.append(row)

            for browser in row_browsers:
                card = BrowserCard(browser, self._on_browser_select)
                self.browser_cards.append(card)
                row.append(card)

        return scroll

    def _on_browser_select(self, selected_card: BrowserCard) -> None:
        """Handle browser selection."""
        for card in self.browser_cards:
            card.set_selected(card == selected_card)

        # Set as default browser (would need actual implementation)
        browser = selected_card.browser
        print(f"Selected browser: {browser.get('label')}")

    def _build_nav(self, parent: Gtk.Box) -> None:
        """Build navigation bar."""
        bar = Gtk.CenterBox()
        bar.add_css_class("bottom-bar")
        parent.append(bar)

        # Startup checkbox
        self.startup_check = Gtk.CheckButton(label=_("Show on startup"))
        self.startup_check.add_css_class("startup-check")
        self.startup_check.set_active(self._is_startup_enabled())
        self.startup_check.connect("toggled", self._on_startup_toggled)
        bar.set_start_widget(self.startup_check)

        # Progress dots
        total = 1 + (len(self.pages_data) if self.pages_data else 0)
        self.progress = ProgressDots(total)
        bar.set_center_widget(self.progress)

        # Navigation buttons
        nav = Gtk.Box(spacing=10)
        bar.set_end_widget(nav)

        self.back_btn = Gtk.Button()
        back_icon = Gtk.Image.new_from_icon_name("go-previous-symbolic")
        back_icon.set_pixel_size(16)
        self.back_btn.set_child(back_icon)
        self.back_btn.add_css_class("nav-button")
        self.back_btn.add_css_class("back")
        self.back_btn.set_visible(False)
        self.back_btn.connect("clicked", self._on_back)
        nav.append(self.back_btn)

        self.next_btn = Gtk.Button()
        next_icon = Gtk.Image.new_from_icon_name("go-next-symbolic")
        next_icon.set_pixel_size(16)
        self.next_btn.set_child(next_icon)
        self.next_btn.add_css_class("nav-button")
        self.next_btn.add_css_class("next")
        self.next_btn.connect("clicked", self._on_next)
        nav.append(self.next_btn)

    def _update_nav(self) -> None:
        """Update navigation state."""
        is_first = self.current_page == 0
        is_last = self.current_page == len(self.page_widgets) - 1

        self.back_btn.set_visible(not is_first)

        if is_last:
            self.next_btn.remove_css_class("nav-button")
            self.next_btn.remove_css_class("next")
            self.next_btn.add_css_class("finish-button")
            self.next_btn.set_child(Gtk.Label(label=_("Get Started")))
        else:
            self.next_btn.add_css_class("nav-button")
            self.next_btn.add_css_class("next")
            self.next_btn.remove_css_class("finish-button")
            icon = Gtk.Image.new_from_icon_name("go-next-symbolic")
            icon.set_pixel_size(16)
            self.next_btn.set_child(icon)

    def _on_back(self, _btn: Gtk.Button) -> None:
        """Go back."""
        if self.current_page > 0:
            self.current_page -= 1
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_RIGHT)
            self._navigate()

    def _on_next(self, _btn: Gtk.Button) -> None:
        """Go next."""
        if self.current_page < len(self.page_widgets) - 1:
            self.current_page += 1
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
            self._navigate()
        else:
            self.close()

    def _navigate(self) -> None:
        """Navigate to current page."""
        if self.current_page == 0:
            self.stack.set_visible_child_name("welcome")
        else:
            self.stack.set_visible_child_name(f"page_{self.current_page - 1}")

        self.progress.set_page(self.current_page)
        self._update_nav()

    def _is_startup_enabled(self) -> bool:
        """Check startup service."""
        try:
            result = subprocess.run(
                ["systemctl", "is-enabled", "big-first-boot.service"],
                capture_output=True,
                text=True,
                check=False,
            )
            return result.returncode == 0
        except OSError:
            return False

    def _on_startup_toggled(self, btn: Gtk.CheckButton) -> None:
        """Toggle startup."""
        action = "enable" if btn.get_active() else "disable"
        try:
            subprocess.Popen(
                ["systemctl", action, "big-first-boot.service"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            pass

    def _parse_os_release(self) -> dict:
        """Parse OS info."""
        info = {}
        try:
            with open("/etc/os-release", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        info[k] = v.strip("\"'")
        except OSError:
            pass
        return info

    def _get_logo_path(self, info: dict) -> str | None:
        """Find logo path."""
        logo = info.get("LOGO", "")
        for path in [
            f"/usr/share/pixmaps/{logo}",
            f"/usr/share/pixmaps/{logo}.png",
            f"/usr/share/pixmaps/{logo}.svg",
        ]:
            if os.path.exists(path):
                return path
        return None


class BigLinuxWelcomeApp(Adw.Application):
    """Main application."""

    def __init__(self) -> None:
        super().__init__(application_id="org.biglinux.welcome")

        # Set color scheme management
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

        self.connect("activate", self._on_activate)
        self._load_css()

    def _load_css(self) -> None:
        """Load CSS."""
        css = Gtk.CssProvider()
        css.load_from_data(PREMIUM_CSS.encode())
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _on_activate(self, _app: Adw.Application) -> None:
        """Activate app."""
        self.win = WelcomeWindow(self)
        self.win.present()


def main() -> None:
    """Entry point."""
    app = BigLinuxWelcomeApp()
    app.run()


if __name__ == "__main__":
    main()
