"""BigLinux Welcome — Application class."""

from __future__ import annotations

import gettext
import os

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, Gtk
from utils import (
    APP_DEVELOPERS,
    APP_ID,
    APP_NAME,
    APP_PATH,
    APP_REPOSITORY,
    APP_VERSION,
    APP_WEBSITE,
)
from window import WelcomeWindow

_ = gettext.gettext


class BigLinuxWelcomeApp(Adw.Application):
    """Main application (single instance: a second launch presents the
    existing window instead of opening another one)."""

    def __init__(self, start_page: int = 0) -> None:
        super().__init__(application_id=APP_ID)
        self.start_page = start_page
        self.win: WelcomeWindow | None = None
        self.connect("startup", self._on_startup)
        self.connect("activate", self._on_activate)

    def _on_startup(self, _app: Adw.Application) -> None:
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.DEFAULT)
        self._load_css()

        about = Gio.SimpleAction.new("about", None)
        about.connect("activate", self._on_about)
        self.add_action(about)

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect(
            "activate", lambda *_a: self.win.close() if self.win else self.quit()
        )
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Control>q"])

    def _load_css(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_path(os.path.join(APP_PATH, "style.css"))
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _on_activate(self, _app: Adw.Application) -> None:
        if self.win is None:
            self.win = WelcomeWindow(self, start_page=self.start_page)
            self.win.connect("destroy", self._on_window_destroyed)
        self.win.present()

    def _on_window_destroyed(self, _win: Gtk.Window) -> None:
        self.win = None

    def _on_about(self, *_args) -> None:
        dialog = Adw.AboutDialog(
            application_name=APP_NAME,
            application_icon="biglinux-welcome",
            version=APP_VERSION,
            developer_name="BigLinux",
            developers=APP_DEVELOPERS,
            website=APP_WEBSITE,
            issue_url=f"{APP_REPOSITORY}/issues",
            comments=_("Initial setup and feature introduction for BigLinux"),
            license_type=Gtk.License.CUSTOM,
            license=_(
                "This program is free software distributed under the GNU General Public License."
            ),
        )
        dialog.add_link(_("Source code"), APP_REPOSITORY)
        dialog.present(self.win)
