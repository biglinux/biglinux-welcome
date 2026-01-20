import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
import locale
import gettext
import subprocess
import threading
import os
from gi.repository import Gtk, Adw, GLib

# Set up gettext for application localization.
DOMAIN = 'biglinux-welcome'
LOCALE_DIR = '/usr/share/locale'
locale.setlocale(locale.LC_ALL, '')
gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.textdomain(DOMAIN)
_ = gettext.gettext

from browser_widget import BrowserWidget

class BrowserPage(Adw.Bin):
    """A page to select, install, and set the default web browser."""
    def __init__(self, page_data, app_path, **kwargs):
        super().__init__(**kwargs)
        self.page_data = page_data
        self.app_path = app_path
        self.script_path = os.path.join(self.app_path, "scripts", "browser.sh")
        self.browser_widgets = []

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=11)
        main_box.set_margin_top(24)
        main_box.set_margin_bottom(24)
        main_box.set_margin_start(36)
        main_box.set_margin_end(36)
        self.set_child(main_box)

        # Title and Subtitle
        title_label = Gtk.Label(halign=Gtk.Align.CENTER)
        title_label.set_markup(f"<span size='xx-large' weight='bold'>{_(page_data['title'])}</span>")
        main_box.append(title_label)

        subtitle_label = Gtk.Label(halign=Gtk.Align.CENTER, wrap=True)
        subtitle_label.set_markup(f"<span size='large'>{_(page_data['subtitle'])}</span>")
        main_box.append(subtitle_label)

        # Spinner for feedback
        self.spinner = Gtk.Spinner(spinning=False, halign=Gtk.Align.CENTER)
        main_box.append(self.spinner)

        # Action Buttons Grid
        self.flowbox = Gtk.FlowBox(valign=Gtk.Align.START, max_children_per_line=5)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_halign(Gtk.Align.CENTER)

        scrolled_window = Gtk.ScrolledWindow(vexpand=True)
        scrolled_window.set_child(self.flowbox)
        scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        main_box.append(scrolled_window)

        for browser in page_data['actions']:
            widget = BrowserWidget(browser, self.app_path)
            widget.button.connect("clicked", self._on_browser_clicked, browser)
            self.browser_widgets.append(widget)
            self.flowbox.insert(widget, -1)

        # Initial state check, deferred to avoid blocking UI thread on startup
        GLib.idle_add(self.refresh_browser_states)

    def _run_script(self, args):
        """Helper to run the browser script and return its output."""
        try:
            cmd = [self.script_path] + args
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            print(f"Error running script with args {args}: {e}")
            return None

    def _is_installed(self, package_name):
        """Check if a browser is installed via the script."""
        output = self._run_script(["check", package_name])
        return output == "true"

    def _get_default_browser(self):
        """Get the .desktop file of the current default browser via the script."""
        return self._run_script(["getBrowser"])

    def refresh_browser_states(self):
        """Update all browser widgets to reflect the current system state."""
        self.flowbox.set_sensitive(False) # Disable during check
        current_browser_default = self._run_script(["getBrowser"])

        for widget in self.browser_widgets:
            browser_data = widget.browser_data
            is_installed = False
            installed_desktop = None

            # Checks each variant (Native or Flatpak) defined in the YAML
            for variant in browser_data.get('variants', []):
                if os.path.exists(variant['check']):
                    is_installed = True
                    installed_desktop = variant['desktop']
                    break # Stops at the first one found installed

            # Checks if it's the default
            is_default = (is_installed and installed_desktop == current_browser_default)

            widget.set_installed(is_installed)
            widget.set_default(is_default)
            # We save which desktop is active to use on click
            widget.detected_desktop = installed_desktop

        self.flowbox.set_sensitive(True)
        self.spinner.stop()
        return GLib.SOURCE_REMOVE

    def _on_browser_clicked(self, button, browser_data):
        """Handle click: install if needed, then set as default."""
        self.flowbox.set_sensitive(False)
        self.spinner.start()

        thread = threading.Thread(target=self._perform_browser_action, args=(browser_data,))
        thread.daemon = True
        thread.start()

    def _perform_browser_action(self, browser_data):
        # Checks if it's installed (using path logic)
        is_installed = any(os.path.exists(v['check']) for v in browser_data.get('variants', []))

        if not is_installed:
            self._run_script(["install", browser_data['package']])

        # After installing, we need to know which .desktop file is available
        # (We run the quick check again)
        desktop_to_set = None
        for variant in browser_data.get('variants', []):
            if os.path.exists(variant['check']):
                desktop_to_set = variant['desktop']
                break

        # Sets it as default using the specific .desktop file
        if desktop_to_set:
            self._run_script(["setBrowser", desktop_to_set])

        GLib.idle_add(self.refresh_browser_states)
