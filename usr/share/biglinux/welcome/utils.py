"""BigLinux Welcome — Utility functions."""

from __future__ import annotations

import os
import platform

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402

APP_PATH = os.path.dirname(os.path.abspath(__file__))


def load_icon(name: str, size: int = 64, subdir: str = "image") -> Gtk.Image:
    """Load icon from local file or theme, with accessible name support."""
    img = None

    if name.endswith((".svg", ".png")):
        path = os.path.join(APP_PATH, subdir, name)
        if os.path.exists(path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
                img = Gtk.Image.new_from_pixbuf(pb)
            except GLib.Error:
                pass

    if img is None:
        img = Gtk.Image.new_from_icon_name(name or "application-x-executable")

    img.set_pixel_size(size)
    return img


def load_browser_icon(package: str, size: int = 64) -> Gtk.Image:
    """Load browser icon from the browsers folder."""
    path = os.path.join(APP_PATH, "image", "browsers", f"{package}.svg")
    img = None

    if os.path.exists(path):
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, size, size)
            img = Gtk.Image.new_from_pixbuf(pb)
        except GLib.Error:
            pass

    if img is None:
        img = Gtk.Image.new_from_icon_name("web-browser-symbolic")

    img.set_pixel_size(size)
    return img


def parse_os_release() -> dict[str, str]:
    """Parse /etc/os-release into a dictionary."""
    try:
        return platform.freedesktop_os_release()
    except OSError:
        info: dict[str, str] = {}
        try:
            with open("/etc/os-release", encoding="utf-8") as f:
                for line in f:
                    if "=" in line:
                        k, v = line.strip().split("=", 1)
                        info[k] = v.strip("\"'")
        except OSError:
            pass
        return info


def get_desktop() -> str:
    """Get the current desktop environment name."""
    de = os.environ.get("XDG_CURRENT_DESKTOP", "")
    if "KDE" in de:
        return "Plasma"
    if "GNOME" in de:
        return "GNOME"
    return de or "Unknown"


def get_logo_path(os_info: dict[str, str]) -> str | None:
    """Find the distribution logo path."""
    logo = os_info.get("LOGO", "")
    for path in [
        f"/usr/share/pixmaps/{logo}",
        f"/usr/share/pixmaps/{logo}.png",
        f"/usr/share/pixmaps/{logo}.svg",
    ]:
        if os.path.exists(path):
            return path
    return None
