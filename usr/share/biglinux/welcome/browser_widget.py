import gi

gi.require_version("Gtk", "4.0")
import os

from gi.repository import GdkPixbuf, GLib, Gtk


class BrowserWidget(Gtk.Box):
    """
    A custom widget to display a browser, indicating its installation
    and default status, and handling clicks to install/set as default.
    """

    def __init__(self, browser_data, app_path, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6, **kwargs)
        self.browser_data = browser_data
        self.app_path = app_path
        self.set_tooltip_text(browser_data["label"])

        self.button = Gtk.Button()
        self.button.set_has_frame(False)
        self.button.add_css_class("flat")
        # The click signal will be connected by the parent page

        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.button.set_child(content_box)

        # Create a fixed-size container. This ensures all icons have the same layout space.
        icon_container = Gtk.Box()
        icon_container.set_size_request(64, 64)

        # Render the SVG to a Pixbuf at the exact target size to ensure sharpness.
        icon_path = os.path.join(
            self.app_path, "image", "browsers", f"{browser_data['package']}.svg"
        )

        # Render the SVG to a Pixbuf at the exact target size to ensure sharpness.
        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(icon_path, 64, 64)
            icon_widget = Gtk.Image.new_from_pixbuf(pixbuf)
            icon_widget.set_pixel_size(64)
        except GLib.Error as e:
            print(f"Error loading icon {icon_path}: {e}. Using fallback.")
            icon_widget = Gtk.Image.new_from_icon_name("image-missing-symbolic")
            icon_widget.set_pixel_size(64)

        # Allow the icon widget to expand and fill the fixed-size container.
        icon_widget.set_hexpand(True)
        icon_widget.set_vexpand(True)
        icon_container.append(icon_widget)

        # Checkmark Overlay
        self.check_icon = Gtk.Image.new_from_icon_name("object-select-symbolic")
        self.check_icon.add_css_class("success")

        self.overlay = Gtk.Overlay()
        self.overlay.set_child(icon_container)
        self.overlay.add_overlay(self.check_icon)
        self.overlay.set_measure_overlay(self.check_icon, True)
        self.check_icon.set_halign(Gtk.Align.END)
        self.check_icon.set_valign(Gtk.Align.END)

        content_box.append(self.overlay)

        # Label
        label_widget = Gtk.Label(label=browser_data["label"])
        label_widget.set_wrap(True)
        label_widget.set_justify(Gtk.Justification.CENTER)
        # Force the label to reserve space for 2 lines to ensure all widgets have the same height
        label_widget.set_lines(2)
        content_box.append(label_widget)

        self.append(self.button)
        self.set_installed(False)
        self.set_default(False)

    def set_installed(self, is_installed):
        """Sets the visual state to installed or not installed."""
        if is_installed:
            self.remove_css_class("is-not-installed")
        else:
            self.add_css_class("is-not-installed")

    def set_default(self, is_default):
        """Shows or hides the default checkmark."""
        self.check_icon.set_visible(is_default)
