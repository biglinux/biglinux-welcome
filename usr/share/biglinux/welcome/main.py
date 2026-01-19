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


class WelcomeAssistant(Gtk.Assistant):
    """A step-by-step assistant for BigLinux welcome setup."""
    
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        
        self.set_default_size(850, 650)
        self.set_title(_("BigLinux Welcome"))
        
        # Load page data from YAML
        self.pages_data = self.load_pages_data()
        if not self.pages_data:
            self.show_error_page()
            return
        
        self.build_pages()
        
        # Create custom Finish button
        self.finish_button = Gtk.Button(label=_("Finish"))
        self.finish_button.add_css_class("suggested-action")
        self.finish_button.connect("clicked", self._on_finish_clicked)
        self.finish_button.set_visible(False)
        self.add_action_widget(self.finish_button)
        
        # Checkbox for "Show on startup"
        self.startup_check = Gtk.CheckButton(label=_("Show on startup"))
        self.startup_check.set_margin_start(12)
        self.startup_check.set_active(self._is_startup_enabled())
        self.startup_check.connect("toggled", self._on_startup_toggled)
        self.add_action_widget(self.startup_check)
        
        # Connect signals
        self.connect("prepare", self.on_prepare)
        self.connect("cancel", self._on_cancel_clicked)
        
        # Customize buttons and sidebar after the assistant is realized
        GLib.idle_add(self.customize_buttons)
        GLib.idle_add(self._make_sidebar_clickable)
    
    def _find_widget_by_type_recursive(self, widget, widget_type):
        """Recursively find a widget by type in the widget hierarchy."""
        if isinstance(widget, widget_type):
            return widget
        
        child = widget.get_first_child() if hasattr(widget, 'get_first_child') else None
        while child:
            result = self._find_widget_by_type_recursive(child, widget_type)
            if result:
                return result
            child = child.get_next_sibling()
        return None
    
    def _make_sidebar_clickable(self):
        """Make the sidebar items clickable for navigation."""
        # Delay to ensure the sidebar is fully built
        GLib.timeout_add(300, self._setup_sidebar_navigation)
        return GLib.SOURCE_REMOVE
    
    def _collect_all_widgets(self, widget, results, depth=0):
        """Collect all widgets in the hierarchy with their info."""
        widget_info = {
            'widget': widget,
            'type': type(widget).__name__,
            'depth': depth
        }
        results.append(widget_info)
        
        child = widget.get_first_child() if hasattr(widget, 'get_first_child') else None
        while child:
            self._collect_all_widgets(child, results, depth + 1)
            child = child.get_next_sibling()
    
    def _setup_sidebar_navigation(self):
        """Setup click navigation on sidebar elements."""
        # Collect all widgets
        all_widgets = []
        self._collect_all_widgets(self, all_widgets)
        
        # Get all page titles to match with labels
        page_titles = []
        for i in range(self.get_n_pages()):
            page = self.get_nth_page(i)
            title = self.get_page_title(page)
            page_titles.append(title)
        
        # Find labels that match page titles
        labels = [w for w in all_widgets if w['type'] == 'Label']
        
        for label_info in labels:
            label = label_info['widget']
            label_text = label.get_label() if hasattr(label, 'get_label') else ""
            
            # Check if this label text matches any page title
            for i, title in enumerate(page_titles):
                if label_text == title:
                    label._page_index = i
                    
                    # Add click gesture
                    gesture = Gtk.GestureClick.new()
                    gesture.set_button(1)
                    gesture.connect("released", self._on_sidebar_item_click)
                    label.add_controller(gesture)
                    break
        
        return GLib.SOURCE_REMOVE
    
    def _on_sidebar_item_click(self, gesture, n_press, x, y):
        """Navigate to the page when a sidebar item is clicked."""
        widget = gesture.get_widget()
        if hasattr(widget, '_page_index'):
            page_index = widget._page_index
            if 0 <= page_index < self.get_n_pages():
                self.set_current_page(page_index)
    
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
        """Constructs all assistant pages."""
        
        # First page: Welcome with system logo and info
        welcome_logo_page = WelcomeLogoPage()
        self.append_page(welcome_logo_page)
        self.set_page_title(welcome_logo_page, _("Welcome"))
        self.set_page_type(welcome_logo_page, Gtk.AssistantPageType.INTRO)
        self.set_page_complete(welcome_logo_page, True)
        
        # Pages from YAML
        for i, page_data in enumerate(self.pages_data):
            # Decide which page type to create
            if page_data.get("page_type") == "browsers":
                page_widget = BrowserPage(page_data, APP_PATH)
            else:
                page_widget = WelcomePage(page_data)
            
            # Add page to assistant
            self.append_page(page_widget)
            
            # Set page title
            self.set_page_title(page_widget, _(page_data.get('title', f'Step {i + 1}')))
            
            # All pages are CONTENT type - we'll handle Finish button ourselves
            self.set_page_type(page_widget, Gtk.AssistantPageType.CONTENT)
            
            # Mark page as complete (allow navigation)
            self.set_page_complete(page_widget, True)
    
    def customize_buttons(self):
        """Customize the assistant buttons: arrows for nav, manage cancel."""
        current_page = self.get_current_page()
        total_pages = self.get_n_pages()
        is_last_page = (current_page == total_pages - 1)
        is_first_page = (current_page == 0)
        self._update_button_labels(is_last_page, is_first_page)
        return GLib.SOURCE_REMOVE
    
    def _find_buttons_recursive(self, widget, buttons):
        """Recursively find all buttons in the widget hierarchy."""
        if isinstance(widget, Gtk.Button):
            buttons.append(widget)
        
        # Check for children
        child = widget.get_first_child() if hasattr(widget, 'get_first_child') else None
        while child:
            self._find_buttons_recursive(child, buttons)
            child = child.get_next_sibling()
    
    def _update_button_labels(self, is_last_page=False, is_first_page=False):
        """Update button labels to use arrows and manage button visibility."""
        buttons = []
        self._find_buttons_recursive(self, buttons)
        
        for button in buttons:
            # Skip our custom finish button
            if button == self.finish_button:
                continue
                
            label = button.get_label()
            icon_name = button.get_icon_name() if hasattr(button, 'get_icon_name') else None
            
            if label:
                label_lower = label.lower()
                
                # Replace Back with arrow
                if 'back' in label_lower or 'voltar' in label_lower or 'anterior' in label_lower:
                    button.set_label("")
                    button.set_icon_name("go-previous-symbolic")
                    button.set_tooltip_text(_("Back"))
                
                # Replace Next/Forward with arrow - hide on last page
                elif 'next' in label_lower or 'forward' in label_lower or 'próximo' in label_lower or 'avançar' in label_lower:
                    button.set_label("")
                    button.set_icon_name("go-next-symbolic")
                    button.set_tooltip_text(_("Next"))
                    if is_last_page:
                        button.set_visible(False)
                    else:
                        button.set_visible(True)
                
                # Cancel button - show only on first page
                elif 'cancel' in label_lower or 'cancelar' in label_lower:
                    if is_first_page:
                        button.set_visible(True)
                        button.set_label(_("Cancel"))
                    else:
                        button.set_visible(False)
                
                # Hide all native finish-type buttons (we have our own)
                elif any(word in label_lower for word in ['finish', 'apply', 'close', 'last', 'concluir', 'finalizar', 'fechar', 'aplicar']):
                    button.set_visible(False)
            
            # Also check for already-customized Next button (by icon)
            elif icon_name == "go-next-symbolic":
                if is_last_page:
                    button.set_visible(False)
                else:
                    button.set_visible(True)
    
    def on_prepare(self, assistant, page):
        """Called when a page is about to be shown."""
        current_page = self.get_current_page()
        total_pages = self.get_n_pages()
        is_last_page = (current_page == total_pages - 1)
        is_first_page = (current_page == 0)
        
        # Update window title with progress
        self.set_title(_("BigLinux Welcome") + f" ({current_page + 1}/{total_pages})")
        
        # Show/hide our custom Finish button based on page
        self.finish_button.set_visible(is_last_page)
        
        # Re-customize native buttons each time page changes
        GLib.idle_add(lambda: self._update_button_labels(is_last_page, is_first_page))
    
    def _on_finish_clicked(self, button):
        """Handle finish button click - close the application."""
        self.destroy()
    
    def _on_cancel_clicked(self, assistant):
        """Handle cancel button click - close the application."""
        self.destroy()
        
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
            # Try to change service status (might need authentication if not user service)
            # Using --user if it's a user service, but request implies system/global service name
            # If it requires root, this might fail silently or show auth dialog depending on policy
            subprocess.Popen(["systemctl", action, "big-first-boot.service"])
        except Exception as e:
            print(f"Error changing service status: {e}")
    
    def show_error_page(self):
        """Displays an error if page data cannot be loaded."""
        error_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        error_box.set_valign(Gtk.Align.CENTER)
        error_box.set_halign(Gtk.Align.CENTER)
        
        error_icon = Gtk.Image.new_from_icon_name("dialog-error-symbolic")
        error_icon.set_pixel_size(64)
        error_box.append(error_icon)
        
        error_title = Gtk.Label()
        error_title.set_markup(f"<b>{_('Could Not Load Welcome Pages')}</b>")
        error_box.append(error_title)
        
        error_desc = Gtk.Label(label=_("Check if 'pages.yaml' exists and is correctly formatted."))
        error_box.append(error_desc)
        
        self.append_page(error_box)
        self.set_page_type(error_box, Gtk.AssistantPageType.SUMMARY)
        self.set_page_title(error_box, _("Error"))
        self.set_page_complete(error_box, True)


class BigLinuxWelcome(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(application_id='org.biglinux.welcome', **kwargs)
        # Set color scheme management as recommended by libadwaita
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
            
            /* Styling for the Assistant Sidebar */
            assistant .sidebar {
                background-color: alpha(@accent_bg_color, 0.1);
            }
            
            assistant .sidebar row {
                padding: 8px 12px;
                border-radius: 6px;
                margin: 2px 6px;
            }
            
            assistant .sidebar row:hover {
                background-color: alpha(@accent_bg_color, 0.2);
            }
            
            assistant .sidebar row:selected {
                background-color: @accent_bg_color;
                color: @accent_fg_color;
            }
            
            assistant .sidebar label {
                padding: 6px 12px;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def on_activate(self, app):
        self.win = WelcomeAssistant(app=app, application=app)
        self.win.present()

if __name__ == "__main__":
    app = BigLinuxWelcome()
    app.run()
