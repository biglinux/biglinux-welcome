"""BigLinux Welcome — Application class."""

from __future__ import annotations

import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gtk  # noqa: E402

from utils import APP_PATH  # noqa: E402
from window import WelcomeWindow  # noqa: E402


class BigLinuxWelcomeApp(Adw.Application):
    """Main application."""

    def __init__(self) -> None:
        super().__init__(application_id="org.biglinux.welcome")

        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

        self.connect("activate", self._on_activate)
        self._load_css()

    def _load_css(self) -> None:
        css = Gtk.CssProvider()
        css_path = os.path.join(APP_PATH, "style.css")
        css.load_from_path(css_path)
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _on_activate(self, _app: Adw.Application) -> None:
        self.win = WelcomeWindow(self)
        self.win.present()
