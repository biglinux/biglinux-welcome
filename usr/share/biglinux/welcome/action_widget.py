import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GLib
import subprocess
import shlex
import locale
import gettext
import os

# Set up gettext for application localization.
DOMAIN = 'biglinux-welcome'
LOCALE_DIR = '/usr/share/locale'
locale.setlocale(locale.LC_ALL, '')
locale.bindtextdomain(DOMAIN, LOCALE_DIR)
locale.textdomain(DOMAIN)
gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.textdomain(DOMAIN)
_ = gettext.gettext

APP_PATH = None

class ActionWidget(Gtk.Box):
    """
    A custom widget that can be either a clickable button with an icon and label,
    or a static image with a label.
    """
    def __init__(self, label, icon_name, action_type, command, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)

        self.action_type = action_type
        self.command = command

        if self.action_type == "image":
            self.build_image_widget(label, icon_name)
        else:
            self.build_button_widget(label, icon_name)

    def build_image_widget(self, label, icon_name):
        """Builds a non-clickable image widget."""
        # Icon/Image
        image_path = os.path.join(APP_PATH, "image", icon_name)
        image = Gtk.Image.new_from_file(image_path)
        image.set_pixel_size(200)
        image.set_halign(Gtk.Align.CENTER)
        self.append(image)

        # Label
        label_widget = Gtk.Label(label=label)
        label_widget.set_wrap(True)
        self.append(label_widget)

    def build_button_widget(self, label, icon_name):
        """Builds a clickable button widget that will be packed into the parent Box."""
        button = Gtk.Button()
        button.set_has_frame(False)
        button.add_css_class("flat")
        button.connect("clicked", self._on_clicked)
        button.set_tooltip_text(label)

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        button.set_child(content_box)

        # Use Gtk.Image, which is simpler for theme icons
        if icon_name.startswith("image/") or "/" in icon_name or icon_name.endswith(".svg") or icon_name.endswith(".png"):
            # Try to load as file relative to APP_PATH
            
            potential_path = os.path.join(APP_PATH, icon_name)
            if not os.path.exists(potential_path) and icon_name.startswith("image/"):
                pass
            
            if os.path.exists(potential_path):
                 icon = Gtk.Image.new_from_file(potential_path)
            else:
                 # Fallback: try inside image/ folder directly if not found
                 icon_path_in_image_folder = os.path.join(APP_PATH, "image", os.path.basename(icon_name))
                 if os.path.exists(icon_path_in_image_folder):
                     icon = Gtk.Image.new_from_file(icon_path_in_image_folder)
                 else:
                     # Fallback to icon name if file not found
                     icon = Gtk.Image.new_from_icon_name(icon_name)
            
            # Use larger size for file images (like QR codes)
            icon.set_pixel_size(200)
        else:
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(64)
            
        content_box.append(icon)

        # Label
        label_widget = Gtk.Label(label=label)
        label_widget.set_wrap(True)
        content_box.append(label_widget)

        self.append(button)

    def _on_clicked(self, widget):
        """Handles the click event and performs the defined action."""
        print(f"Action triggered: type='{self.action_type}', command='{self.command}'")
        try:
            if self.action_type == "script":
                script_path = os.path.join(APP_PATH, self.command)
                command_parts = shlex.split(script_path)
                subprocess.Popen(command_parts)
            elif self.action_type == "app":
                command_parts = shlex.split(self.command)
                subprocess.Popen(command_parts)
            elif self.action_type == "url":
                Gtk.show_uri(None, self.command, Gdk.CURRENT_TIME)
        except Exception as e:
            print(f"Failed to execute command '{self.command}': {e}")
