#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
import os
import yaml
import locale
import gettext
from gi.repository import Gtk, Adw, Gio, Gdk, GLib
import subprocess
from welcome_page import WelcomePage
from browser_page import BrowserPage
from welcome_logo_page import WelcomeLogoPage
import action_widget

# Set up gettext for application localization.
DOMAIN = 'biglinux-welcome'
LOCALE_DIR = '/usr/share/locale'
locale.setlocale(locale.LC_ALL, '')
locale.bindtextdomain(DOMAIN, LOCALE_DIR)
locale.textdomain(DOMAIN)
gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.textdomain(DOMAIN)
_ = gettext.gettext

# Define a base path for the application's resources
APP_PATH = os.path.dirname(os.path.abspath(__file__))
action_widget.APP_PATH = APP_PATH


class WelcomeWindow(Adw.ApplicationWindow):
    """A window using libadwaita components for BigLinux welcome."""
    
    def __init__(self, app, **kwargs):
        super().__init__(application=app, **kwargs)
        
        self.set_default_size(950, 700)
        self.set_title(_("BigLinux Welcome"))
        
        # Load page data
        self.pages_data = self.load_pages_data()
        
        # Main content structure
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(content)
        
        # Header Bar
        header = Adw.HeaderBar()
        content.append(header)
        
        # View Stack
        self.stack = Adw.ViewStack()
        
        # View Switcher in Header (Scrollable)
        switcher = Adw.ViewSwitcher()
        switcher.set_stack(self.stack)
        
        switcher_scroll = Gtk.ScrolledWindow()
        switcher_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        switcher_scroll.set_child(switcher)
        switcher_scroll.set_has_frame(False)
        switcher_scroll.set_propagate_natural_width(True)
        
        header.set_title_widget(switcher_scroll)
        
        # Add pages to the stack
        self.build_pages()
        
        # Stack needs to expand to fill space
        stack_wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        stack_wrapper.set_vexpand(True)
        stack_wrapper.append(self.stack)
        content.append(stack_wrapper)
        
        # Bottom Bar (Action Bar)
        action_bar = Gtk.ActionBar()
        content.append(action_bar)
        
        # Startup Checkbox
        self.startup_check = Gtk.CheckButton(label=_("Show on startup"))
        self.startup_check.set_margin_start(12)
        self.startup_check.set_margin_end(12)
        self.startup_check.set_active(self._is_startup_enabled())
        self.startup_check.connect("toggled", self._on_startup_toggled)
        action_bar.pack_start(self.startup_check)
        
        # Navigation Buttons Box
        nav_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_bar.pack_end(nav_box)

        # Back Button
        self.back_btn = Gtk.Button.new_from_icon_name("go-previous-symbolic")
        self.back_btn.add_css_class("suggested-action")
        self.back_btn.set_tooltip_text(_("Back"))
        self.back_btn.connect("clicked", self._on_back_clicked)
        nav_box.append(self.back_btn)

        # Next/Close Button
        self.next_btn = Gtk.Button.new_from_icon_name("go-next-symbolic")
        self.next_btn.add_css_class("suggested-action")
        self.next_btn.set_tooltip_text(_("Next"))
        self.next_btn.connect("clicked", self._on_next_clicked)
        nav_box.append(self.next_btn)
        
        # Connect stack signal to update buttons
        self.stack.connect("notify::visible-child", self._on_stack_page_changed)
        
        # Initial button state update
        GLib.idle_add(self._update_navigation_buttons)

    def _on_back_clicked(self, button):
        """Navigate to the previous page."""
        try:
            pages = self.stack.get_pages()
            current_page = self.stack.get_visible_child()
            
            prev_page = None
            for i in range(pages.get_n_items()):
                page_info = pages.get_item(i)
                child = page_info.get_child()
                if child == current_page:
                    if prev_page:
                        self.stack.set_visible_child(prev_page)
                    break
                prev_page = child
        except Exception as e:
            print(f"Error in back navigation: {e}")

    def _on_next_clicked(self, button):
        """Navigate to the next page or close if on the last page."""
        try:
            pages = self.stack.get_pages()
            current_page = self.stack.get_visible_child()
            n_items = pages.get_n_items()
            
            # Check if we are on the last page
            last_page_info = pages.get_item(n_items - 1)
            if current_page == last_page_info.get_child():
                self.close()
                return

            # Find current and switch to next
            for i in range(n_items - 1):
                page_info = pages.get_item(i)
                if page_info.get_child() == current_page:
                    next_page_info = pages.get_item(i + 1)
                    self.stack.set_visible_child(next_page_info.get_child())
                    break
        except Exception as e:
            print(f"Error in next navigation: {e}")
            # Fallback to close if error occurs (safety)
            self.close()

    def _on_stack_page_changed(self, stack, param):
        """Update button visibility when page changes."""
        self._update_navigation_buttons()

    def _update_navigation_buttons(self):
        """Enable/Disable back button and change Next to Close on last page."""
        try:
            pages = self.stack.get_pages()
            n_items = pages.get_n_items()
            if n_items == 0:
                print("No pages in stack")
                return

            current_page = self.stack.get_visible_child()
            if not current_page:
                return
            
            # Check if first page
            first_page_info = pages.get_item(0)
            is_first = (current_page == first_page_info.get_child())
            
            # Check if last page
            last_page_info = pages.get_item(n_items - 1)
            is_last = (current_page == last_page_info.get_child())
            
            # Update Back Button
            self.back_btn.set_sensitive(not is_first)
            self.back_btn.set_visible(not is_first)
            
            # Update Next Button
            if is_last:
                self.next_btn.set_icon_name("window-close-symbolic")
                self.next_btn.set_tooltip_text(_("Close"))
            else:
                self.next_btn.set_icon_name("go-next-symbolic")
                self.next_btn.set_tooltip_text(_("Next"))
        except Exception as e:
            print(f"Error updating nav buttons: {e}")
            # Ensure buttons are visible in case of error
            self.next_btn.set_visible(True)
            self.back_btn.set_visible(True)

    def load_pages_data(self):
        """Loads page definitions from pages.yaml."""
        yaml_path = os.path.join(APP_PATH, "pages.yaml")
        try:
            with open(yaml_path, "r") as f:
                return yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError) as e:
            print(f"Error loading {yaml_path}: {e}")
            return None

    def build_pages(self):
        """Constructs all pages and adds them to the ViewStack."""
        
        # 1. Welcome Logo Page
        welcome_logo_page = WelcomeLogoPage()
        
        # Add to stack
        self.stack.add_titled_with_icon(
            welcome_logo_page,
            "welcome",
            _("Welcome"),
            "start-here-symbolic" 
        )
        
        # 2. Pages from YAML
        if self.pages_data:
            for i, page_data in enumerate(self.pages_data):
                # Decide which page type to create
                if page_data.get("page_type") == "browsers":
                    page_widget = BrowserPage(page_data, APP_PATH)
                else:
                    page_widget = WelcomePage(page_data)
                
                title = _(page_data.get('title', f'Page {i + 1}'))
                icon = page_data.get('icon', 'help-about-symbolic')
                name = f"page_{i}"
                
                self.stack.add_titled_with_icon(
                    page_widget,
                    name,
                    title,
                    icon
                )

    def _is_startup_enabled(self):
        """Check if big-first-boot.service is enabled."""
        try:
            # Check if service is enabled
            result = subprocess.run(
                ["systemctl", "is-enabled", "big-first-boot.service"],
                capture_output=True, text=True
            )
            return result.returncode == 0
        except Exception as e:
            print(f"Error checking service status: {e}")
            return False

    def _on_startup_toggled(self, button):
        """Enable or disable big-first-boot.service."""
        active = button.get_active()
        action = "enable" if active else "disable"
        
        try:
            subprocess.Popen(["systemctl", action, "big-first-boot.service"])
        except Exception as e:
            print(f"Error changing service status: {e}")


class BigLinuxWelcome(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(application_id='org.biglinux.welcome', **kwargs)
        
        # Set color scheme management
        style_manager = Adw.StyleManager.get_default()
        style_manager.set_color_scheme(Adw.ColorScheme.DEFAULT)

        self.connect('activate', self.on_activate)
        self.load_css()

    def load_css(self):
        """Loads custom CSS for the application."""
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(
            b"""
            .is-not-installed image,
            .is-not-installed picture {
                 filter: grayscale(1);
                 opacity: 0.7;
             }
             
             /* Dim label style */
             .dim-label {
                 opacity: 0.7;
             }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_activate(self, app):
        self.win = WelcomeWindow(app=app)
        self.win.present()

if __name__ == "__main__":
    app = BigLinuxWelcome()
    app.run()
