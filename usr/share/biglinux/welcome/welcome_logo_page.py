import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
import gettext
import locale
import os
import platform
import subprocess

from gi.repository import Adw, Gtk, GdkPixbuf, GLib

# Set up gettext for application localization.
DOMAIN = "biglinux-welcome"
LOCALE_DIR = "/usr/share/locale"
locale.setlocale(locale.LC_ALL, "")
locale.bindtextdomain(DOMAIN, LOCALE_DIR)
locale.textdomain(DOMAIN)
gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.textdomain(DOMAIN)
_ = gettext.gettext


def parse_os_release():
    """Parse /etc/os-release and return a dictionary."""
    os_info = {}
    os_release_path = "/etc/os-release"
    
    if os.path.exists(os_release_path):
        try:
            with open(os_release_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line:
                        key, value = line.split("=", 1)
                        # Remove quotes from value
                        value = value.strip('"').strip("'")
                        os_info[key] = value
        except Exception as e:
            print(f"Error reading {os_release_path}: {e}")
    
    return os_info


def get_logo_path(os_info):
    """Get the logo path from os-release or use a fallback."""
    logo_name = os_info.get("LOGO", "")
    
    # Common locations for logos
    search_paths = [
        f"/usr/share/pixmaps/{logo_name}",
        f"/usr/share/pixmaps/{logo_name}.png",
        f"/usr/share/pixmaps/{logo_name}.svg",
        f"/usr/share/icons/hicolor/scalable/apps/{logo_name}.svg",
        f"/usr/share/icons/hicolor/256x256/apps/{logo_name}.png",
        f"/usr/share/icons/hicolor/128x128/apps/{logo_name}.png",
    ]
    
    for path in search_paths:
        if os.path.exists(path):
            return path
    
    # Fallback to a generic icon
    return None


def get_graphics_platform():
    """Get the graphics platform (Wayland or X11)."""
    xdg_session = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if xdg_session == "wayland":
        return "Wayland"
    elif xdg_session == "x11":
        return "X11"
    
    # Fallback check
    if os.environ.get("WAYLAND_DISPLAY"):
        return "Wayland"
    elif os.environ.get("DISPLAY"):
        return "X11"
    
    return _("Unknown")


def get_desktop_info():
    """Get desktop environment name and version."""
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    version = ""
    
    if "KDE" in desktop or "plasma" in desktop.lower():
        # Get Plasma version
        try:
            result = subprocess.run(
                ["plasmashell", "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Output: "plasmashell 6.x.x"
                version = result.stdout.strip().split()[-1] if result.stdout else ""
        except Exception:
            pass
        return f"Plasma {version}".strip()
    
    elif "GNOME" in desktop:
        # Get GNOME version
        try:
            result = subprocess.run(
                ["gnome-shell", "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                # Output: "GNOME Shell 4x.x"
                version = result.stdout.strip().split()[-1] if result.stdout else ""
        except Exception:
            pass
        return f"GNOME {version}".strip()
    
    elif "XFCE" in desktop:
        try:
            result = subprocess.run(
                ["xfce4-session", "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'xfce4-session' in line:
                        version = line.split()[-1] if line else ""
                        break
        except Exception:
            pass
        return f"XFCE {version}".strip()
    
    return desktop if desktop else _("Unknown")


def get_package_counts():
    """Get package counts for pacman, flatpak, and snap."""
    counts = []
    
    # Pacman packages
    try:
        result = subprocess.run(
            ["pacman", "-Q"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            pacman_count = len(result.stdout.strip().split('\n'))
            counts.append(f"Pacman: {pacman_count}")
    except Exception:
        pass
    
    # Flatpak packages
    try:
        result = subprocess.run(
            ["flatpak", "list", "--app"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            flatpak_count = len([l for l in result.stdout.strip().split('\n') if l])
            counts.append(f"Flatpak: {flatpak_count}")
    except Exception:
        pass
    
    # Snap packages (skip header line)
    #try:
    #    result = subprocess.run(
    #        ["snap", "list"],
    #        capture_output=True, text=True, timeout=10
    #    )
    #    if result.returncode == 0:
    #        lines = result.stdout.strip().split('\n')
    #        snap_count = len(lines) - 1 if len(lines) > 1 else 0  # Skip header
    #        if snap_count > 0:
    #            counts.append(f"Snap: {snap_count}")
    #except Exception:
    #    pass
    
    return " | ".join(counts) if counts else _("Unknown")


class WelcomeLogoPage(Adw.Bin):
    """A welcome page displaying the system logo and information, similar to KDE Plasma's About."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Get OS information
        os_info = parse_os_release()
        
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24)
        main_box.set_valign(Gtk.Align.CENTER)
        main_box.set_halign(Gtk.Align.CENTER)
        self.set_child(main_box)
        
        # Logo
        logo_path = get_logo_path(os_info)
        if logo_path:
            try:
                # Load and display the logo
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(logo_path, 150, 150)
                logo_image = Gtk.Image.new_from_pixbuf(pixbuf)
            except GLib.Error as e:
                print(f"Error loading logo: {e}")
                logo_image = Gtk.Image.new_from_icon_name("distributor-logo")
        else:
            # Fallback icon
            logo_image = Gtk.Image.new_from_icon_name("distributor-logo")          
        
        logo_image.set_halign(Gtk.Align.CENTER)
        logo_image.set_pixel_size(150)
        main_box.append(logo_image)
        
        # Distribution name
        distro_name = os_info.get("PRETTY_NAME", os_info.get("NAME", "Linux"))
        name_label = Gtk.Label()
        name_label.set_markup(f"<span size='xx-large' weight='bold'>{distro_name}</span>")
        name_label.set_halign(Gtk.Align.CENTER)
        name_label.set_wrap(True)
        name_label.set_justify(Gtk.Justification.CENTER)
        main_box.append(name_label)
        
        # Version info
        version = os_info.get("VERSION", os_info.get("VERSION_ID", ""))
        if version:
            version_label = Gtk.Label()
            version_label.set_markup(f"<span size='large'>{_('Version')} {version}</span>")
            version_label.set_halign(Gtk.Align.CENTER)
            version_label.add_css_class("dim-label")
            main_box.append(version_label)
        
        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(12)
        separator.set_margin_bottom(12)
        main_box.append(separator)
        
        # System information grid
        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(8)
        info_grid.set_column_spacing(24)
        info_grid.set_halign(Gtk.Align.CENTER)
        main_box.append(info_grid)
        
        row = 0
        
        # Kernel
        kernel_version = platform.release()
        self._add_info_row(info_grid, row, _("Kernel"), kernel_version)
        row += 1
        
        # Graphics Platform (Wayland/X11)
        graphics_platform = get_graphics_platform()
        self._add_info_row(info_grid, row, _("Graphics"), graphics_platform)
        row += 1
        
        # Desktop Environment with version
        desktop_info = get_desktop_info()
        self._add_info_row(info_grid, row, _("Desktop"), desktop_info)
        row += 1
        
        # Architecture
        arch = platform.machine()
        self._add_info_row(info_grid, row, _("Architecture"), arch)
        row += 1
        
        # Package counts
        package_info = get_package_counts()
        self._add_info_row(info_grid, row, _("Packages"), package_info)
        row += 1
        
        # Home URL
        home_url = os_info.get("HOME_URL", "")
        if home_url:
            link_button = Gtk.LinkButton(uri=home_url, label=home_url)
            link_button.set_halign(Gtk.Align.CENTER)
            link_button.set_margin_top(12)
            main_box.append(link_button)
        
        # Welcome message
        welcome_label = Gtk.Label()
        welcome_label.set_markup(
            f"<span size='medium'>{_('Welcome! This assistant will help you configure your system.')}</span>"
        )
        welcome_label.set_halign(Gtk.Align.CENTER)
        welcome_label.set_wrap(True)
        welcome_label.set_justify(Gtk.Justification.CENTER)
        welcome_label.set_margin_top(24)
        welcome_label.add_css_class("dim-label")
        main_box.append(welcome_label)
    
    def _add_info_row(self, grid, row, label_text, value_text):
        """Add an information row to the grid."""
        label = Gtk.Label(label=f"{label_text}:")
        label.set_halign(Gtk.Align.END)
        label.add_css_class("dim-label")
        grid.attach(label, 0, row, 1, 1)
        
        value = Gtk.Label(label=value_text)
        value.set_halign(Gtk.Align.START)
        value.set_selectable(True)
        grid.attach(value, 1, row, 1, 1)
