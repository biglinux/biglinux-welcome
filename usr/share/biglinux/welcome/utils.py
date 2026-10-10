"""BigLinux Welcome — Utility functions."""

from __future__ import annotations

import math
import os
import platform
import sys

import gi
import yaml

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("GdkPixbuf", "2.0")

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

APP_PATH = os.path.dirname(os.path.abspath(__file__))

APP_ID = "org.biglinux.welcome"
APP_NAME = "BigLinux Welcome"
APP_VERSION = "3.0.0"
APP_WEBSITE = "https://www.biglinux.com.br"
APP_REPOSITORY = "https://github.com/ruscher/biglinux-welcome"
APP_DEVELOPERS = ["Rafael Ruscher", "Bruno Gonçalves", "Barnabé Di Kartola"]


def render_scale() -> int:
    """Integer scale for rasterizing SVGs crisply on every monitor.

    Fractional scales (e.g. 125%) round up, so icons are downscaled
    instead of blurred."""
    display = Gdk.Display.get_default()
    scale = 1.0
    if display is not None:
        monitors = display.get_monitors()
        for i in range(monitors.get_n_items()):
            monitor = monitors.get_item(i)
            get_scale = getattr(monitor, "get_scale", None)
            value = get_scale() if get_scale else monitor.get_scale_factor()
            scale = max(scale, value)
    return max(1, math.ceil(scale))


def _image_from_file(path: str, size: int) -> Gtk.Image | None:
    """Rasterize with librsvg/GdkPixbuf at device scale for crisp HiDPI."""
    if not os.path.exists(path):
        return None
    pixels = size * render_scale()
    try:
        pb = GdkPixbuf.Pixbuf.new_from_file_at_size(path, pixels, pixels)
    except GLib.Error:
        return None
    return Gtk.Image.new_from_paintable(Gdk.Texture.new_for_pixbuf(pb))


def image_path(name: str, subdir: str = "image") -> str:
    """Absolute path of a bundled image."""
    return os.path.join(APP_PATH, subdir, name)


def load_icon(name: str, size: int = 64, subdir: str = "image") -> Gtk.Image:
    """Load an icon from a bundled file or the icon theme."""
    img = None
    if name.endswith((".svg", ".png")):
        img = _image_from_file(image_path(name, subdir), size)
    if img is None:
        img = Gtk.Image.new_from_icon_name(name or "application-x-executable")
    img.set_pixel_size(size)
    return img


def load_browser_icon(icon: str, size: int = 64) -> Gtk.Image:
    """Load a browser icon from the browsers folder."""
    img = _image_from_file(image_path(f"browsers/{icon}.svg"), size)
    if img is None:
        img = Gtk.Image.new_from_icon_name("web-browser-symbolic")
    img.set_pixel_size(size)
    return img


def load_pages(path: str) -> list[dict]:
    """Load pages.yaml, keeping only well-formed pages and actions.

    A malformed entry is skipped (and reported) instead of breaking the
    whole window."""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        print(f"Could not load {path}: {e}", file=sys.stderr)
        return []
    if not isinstance(data, list):
        return []

    pages = []
    for page in data:
        if not isinstance(page, dict) or not isinstance(page.get("title"), str):
            print(f"Ignoring invalid page in {path}: {page!r}", file=sys.stderr)
            continue
        actions = page.get("actions") or []
        page = dict(page)
        page["actions"] = (
            [
                a
                for a in actions
                if isinstance(a, dict) and isinstance(a.get("label"), str)
            ]
            if isinstance(actions, list)
            else []
        )
        pages.append(page)
    return pages


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
