"""BigLinux Welcome — Main window."""

from __future__ import annotations

import gettext
import os
import select
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import yaml  # noqa: E402
from gi.repository import Adw, GdkPixbuf, GLib, Gtk  # noqa: E402

from utils import APP_PATH, get_logo_path, parse_os_release  # noqa: E402
from widgets import (  # noqa: E402
    ActionCard,
    AnimatedLogo,
    BrowserCard,
    InfoCard,
    InstallPanel,
    ProgressDots,
)

_ = gettext.gettext


def _flush_line_buffer(buf: bytes, panel: InstallPanel) -> bytes:
    """Extract complete lines from buf, dispatch to panel, return remainder."""
    while b"\n" in buf or b"\r" in buf:
        idx_n = buf.find(b"\n")
        idx_r = buf.find(b"\r")
        is_newline = idx_n >= 0 and (idx_r < 0 or idx_n <= idx_r)
        if is_newline:
            line = buf[:idx_n].decode("utf-8", errors="replace")
            buf = buf[idx_n + 1 :]
        elif idx_r >= 0:
            line = buf[:idx_r].decode("utf-8", errors="replace")
            buf = buf[idx_r + 1 :]
        else:
            break
        if not line or line.startswith("STATUS:"):
            continue
        if is_newline:
            GLib.idle_add(panel.append_log, line)
        else:
            GLib.idle_add(panel.parse_progress, line)
    return buf


class WelcomeWindow(Adw.ApplicationWindow):
    """Main welcome window."""

    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)
        self.set_default_size(1000, 780)
        self.set_title("BigLinux Welcome")

        self.pages_data = self._load_pages()
        self.current_page = 0
        self.page_widgets: list[Gtk.Widget] = []
        self.browser_cards: list[BrowserCard] = []

        self._build_ui()

    def _load_pages(self) -> list | None:
        try:
            with open(os.path.join(APP_PATH, "pages.yaml"), encoding="utf-8") as f:
                return yaml.safe_load(f)
        except (FileNotFoundError, yaml.YAMLError):
            return None

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main)

        header = Adw.HeaderBar()
        header.add_css_class("flat")
        header.set_show_title(False)
        main.append(header)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(320)
        self.stack.set_vexpand(True)
        main.append(self.stack)

        self._build_pages()
        self._build_nav(main)

    def _build_pages(self) -> None:
        welcome = self._build_welcome()
        self.stack.add_named(welcome, "welcome")
        self.page_widgets.append(welcome)

        if self.pages_data:
            for i, data in enumerate(self.pages_data):
                if data.get("page_type") == "browsers":
                    page = self._build_browser_page(data)
                else:
                    page = self._build_action_page(data)
                self.stack.add_named(page, f"page_{i}")
                self.page_widgets.append(page)

    def _build_welcome(self) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        main.set_valign(Gtk.Align.CENTER)
        main.set_halign(Gtk.Align.CENTER)
        main.set_margin_top(0)
        main.set_margin_bottom(8)
        scroll.set_child(main)

        os_info = parse_os_release()

        # Logo with animated glow
        logo_path = get_logo_path(os_info)
        if logo_path and os.path.exists(logo_path):
            try:
                pb = GdkPixbuf.Pixbuf.new_from_file_at_size(logo_path, 130, 130)
                logo = Gtk.Image.new_from_pixbuf(pb)
            except GLib.Error:
                logo = Gtk.Image.new_from_icon_name("distributor-logo")
        else:
            logo = Gtk.Image.new_from_icon_name("distributor-logo")

        logo.set_pixel_size(130)
        logo.set_halign(Gtk.Align.CENTER)
        logo.set_valign(Gtk.Align.CENTER)
        logo.add_css_class("logo-image")

        logo_overlay = Gtk.Overlay()
        logo_overlay.set_halign(Gtk.Align.CENTER)

        self.logo_animation = AnimatedLogo(logo)
        logo_overlay.set_child(self.logo_animation)
        logo_overlay.add_overlay(logo)
        main.append(logo_overlay)

        # Title — hide distro name when it's BigLinux (logo is enough)
        distro = os_info.get("PRETTY_NAME", "BigLinux")
        is_biglinux = "biglinux" in distro.lower()

        if is_biglinux:
            subtitle_text = _("In search of the perfect system!")
        else:
            title = Gtk.Label(label=distro)
            title.add_css_class("hero-title")
            main.append(title)
            subtitle_text = _("Welcome to your new system")

        # Subtitle
        subtitle = Gtk.Label(label=subtitle_text)
        subtitle.add_css_class("hero-subtitle")
        main.append(subtitle)

        # Version badge
        version = os_info.get("VERSION", "")
        if version:
            badge = Gtk.Label(label=f"v{version}")
            badge.add_css_class("hero-version")
            main.append(badge)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_size_request(-1, 10)
        main.append(spacer)

        # Info card
        main.append(InfoCard())

        return scroll

    def _build_action_page(self, data: dict) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        main.set_margin_top(28)
        main.set_margin_bottom(32)
        main.set_margin_start(40)
        main.set_margin_end(40)
        scroll.set_child(main)

        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header.set_halign(Gtk.Align.CENTER)
        main.append(header)

        title = Gtk.Label(label=_(data.get("title", "")))
        title.add_css_class("page-title")
        # Accessibility: mark as heading
        title.update_property(
            [Gtk.AccessibleProperty.LABEL], [_(data.get("title", ""))]
        )
        header.append(title)

        subtitle = data.get("subtitle", "")
        if subtitle:
            sub = Gtk.Label(label=_(subtitle))
            sub.add_css_class("page-subtitle")
            sub.set_wrap(True)
            sub.set_max_width_chars(60)
            sub.set_justify(Gtk.Justification.CENTER)
            header.append(sub)

        actions = data.get("actions", [])
        items_per_row = 4
        cards_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        cards_container.set_halign(Gtk.Align.CENTER)
        main.append(cards_container)

        for i in range(0, len(actions), items_per_row):
            row_actions = actions[i : i + items_per_row]
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
            row.set_halign(Gtk.Align.CENTER)
            cards_container.append(row)

            for action in row_actions:
                card = ActionCard(action)
                row.append(card)

        return scroll

    def _build_browser_page(self, data: dict) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        main.set_margin_top(28)
        main.set_margin_bottom(32)
        main.set_margin_start(40)
        main.set_margin_end(40)
        scroll.set_child(main)

        # -- Header (always visible, even during install) --
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header.set_halign(Gtk.Align.CENTER)
        main.append(header)

        title = Gtk.Label(label=_(data.get("title", "")))
        title.add_css_class("page-title")
        title.update_property(
            [Gtk.AccessibleProperty.LABEL], [_(data.get("title", ""))]
        )
        header.append(title)

        subtitle = data.get("subtitle", "")
        if subtitle:
            sub = Gtk.Label(label=_(subtitle))
            sub.add_css_class("page-subtitle")
            sub.set_wrap(True)
            sub.set_max_width_chars(55)
            sub.set_justify(Gtk.Justification.CENTER)
            header.append(sub)

        # -- Inner stack: cards grid ↔ install panel --
        self.browser_stack = Gtk.Stack()
        self.browser_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.browser_stack.set_transition_duration(280)
        self.browser_stack.set_vexpand(True)
        main.append(self.browser_stack)

        # Cards grid
        cards_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        cards_container.set_halign(Gtk.Align.CENTER)
        cards_container.set_valign(Gtk.Align.START)

        browsers = data.get("actions", [])
        items_per_row = 5
        self.browser_cards = []
        for i in range(0, len(browsers), items_per_row):
            row_browsers = browsers[i : i + items_per_row]
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
            row.set_halign(Gtk.Align.CENTER)
            cards_container.append(row)

            for browser in row_browsers:
                card = BrowserCard(browser, self._on_browser_select)
                self.browser_cards.append(card)
                row.append(card)

        self.browser_stack.add_named(cards_container, "browsers")

        # Install panel placeholder (replaced dynamically)
        placeholder = Gtk.Box()
        self.browser_stack.add_named(placeholder, "installing")

        # -- Loading overlay for "set default" --
        self._browser_loading_overlay = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12
        )
        self._browser_loading_overlay.set_halign(Gtk.Align.CENTER)
        self._browser_loading_overlay.set_valign(Gtk.Align.CENTER)
        self._browser_loading_overlay.set_visible(False)
        self._browser_loading_overlay.add_css_class("browser-loading-overlay")

        self._browser_loading_spinner = Gtk.Spinner()
        self._browser_loading_spinner.set_size_request(48, 48)
        self._browser_loading_overlay.append(self._browser_loading_spinner)

        self._browser_loading_label = Gtk.Label(label="")
        self._browser_loading_label.add_css_class("page-subtitle")
        self._browser_loading_overlay.append(self._browser_loading_label)
        self._browser_loading_overlay.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Changing default browser")],
        )

        page_overlay = Gtk.Overlay()
        page_overlay.set_child(scroll)
        page_overlay.add_overlay(self._browser_loading_overlay)

        GLib.idle_add(self.refresh_browser_states)
        return page_overlay

    # ------------------------------------------------------------------
    # Browser logic
    # ------------------------------------------------------------------

    def _run_browser_script(self, args: list[str]) -> str:
        script_path = os.path.join(APP_PATH, "scripts", "browser.sh")
        try:
            cmd = [script_path] + args
            result = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=300
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            print(f"Error running browser script {args}: {e}")
            return ""

    def refresh_browser_states(self) -> bool:
        current_browser_default = self._run_browser_script(["getBrowser"])

        for card in self.browser_cards:
            is_installed = False
            installed_desktop = None

            for variant in card.browser.get("variants", []):
                check_path = variant.get("check", "")
                if check_path and os.path.exists(check_path):
                    is_installed = True
                    installed_desktop = variant.get("desktop", "")
                    break

            card.set_installed(is_installed)
            card.detected_desktop = installed_desktop
            card.set_selected(
                is_installed and installed_desktop == current_browser_default
            )

        return GLib.SOURCE_REMOVE

    def _on_browser_select(self, selected_card: BrowserCard) -> None:
        browser = selected_card.browser

        # If already installed, just set as default (no panel needed)
        is_installed = any(
            os.path.exists(v.get("check", "")) for v in browser.get("variants", [])
        )
        if is_installed:
            thread = threading.Thread(
                target=self._set_default_browser, args=(selected_card,), daemon=True
            )
            thread.start()
            return

        # Not installed → show integrated install panel
        self._start_install(selected_card)

    def _set_default_browser(self, card: BrowserCard) -> None:
        """Set an already-installed browser as default (background thread)."""
        browser_label = card.browser.get("label", "")
        GLib.idle_add(self._show_browser_loading, browser_label)
        try:
            desktop_to_set = None
            for variant in card.browser.get("variants", []):
                if os.path.exists(variant.get("check", "")):
                    desktop_to_set = variant.get("desktop", "")
                    break
            if desktop_to_set:
                self._run_browser_script(["setBrowser", desktop_to_set])
        finally:
            GLib.idle_add(self._hide_browser_loading, browser_label)
            GLib.idle_add(self.refresh_browser_states)

    def _show_browser_loading(self, browser_label: str) -> None:
        self._browser_loading_label.set_label(
            _("Setting %s as default…") % browser_label
        )
        self._browser_loading_overlay.set_visible(True)
        self._browser_loading_spinner.start()
        for card in self.browser_cards:
            card.set_sensitive(False)

    def _hide_browser_loading(self, browser_label: str = "") -> None:
        self._browser_loading_spinner.stop()
        for card in self.browser_cards:
            card.set_sensitive(True)
        if browser_label:
            self._browser_loading_label.set_label(
                _("%s set as default") % browser_label
            )
            GLib.timeout_add(1500, self._dismiss_browser_overlay)
        else:
            self._browser_loading_overlay.set_visible(False)

    def _dismiss_browser_overlay(self) -> bool:
        self._browser_loading_overlay.set_visible(False)
        return GLib.SOURCE_REMOVE

    def _start_install(self, card: BrowserCard) -> None:
        """Show the install panel and start the install process."""
        browser = card.browser
        browser_label = browser.get("label", "")
        package = browser.get("package", "")
        icon_path = (
            os.path.join(APP_PATH, "image", "browsers", f"{package}.svg")
            if package
            else None
        )

        # Create and attach the install panel
        panel = InstallPanel(browser_label, icon_path)
        panel.set_done_callback(lambda: self._finish_install(browser_label))

        # Store proc reference for cancel support
        self._install_proc: subprocess.Popen[bytes] | None = None
        panel.set_cancel_callback(self._cancel_install)

        # Replace the installing page in the stack
        old = self.browser_stack.get_child_by_name("installing")
        if old:
            self.browser_stack.remove(old)
        self.browser_stack.add_named(panel, "installing")
        self.browser_stack.set_visible_child_name("installing")

        # Disable navigation during install
        self._set_nav_sensitive(False)

        # Start pulse animation and background install
        panel.start_pulse()
        self._install_panel = panel

        thread = threading.Thread(
            target=self._perform_browser_install,
            args=(card, panel),
            daemon=True,
        )
        thread.start()

    def _cancel_install(self) -> None:
        """Kill the running installation subprocess."""
        proc = getattr(self, "_install_proc", None)
        if proc and proc.poll() is None:
            proc.terminate()

    def _perform_browser_install(self, card: BrowserCard, panel: InstallPanel) -> None:
        """Run browser installation script, reading output in real time."""
        browser = card.browser
        browser_label = browser.get("label", "")
        package = browser.get("package", "")
        script_path = os.path.join(APP_PATH, "scripts", "browser.sh")

        success = False
        try:
            proc = subprocess.Popen(
                [script_path, "install", package],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                bufsize=0,
            )
            self._install_proc = proc

            if proc.stdout is None:
                raise OSError("Failed to capture process output")

            self._read_process_output(proc, panel)
            proc.wait(timeout=600)
            success = proc.returncode == 0 and not panel.cancelled

        except (OSError, subprocess.TimeoutExpired) as e:
            GLib.idle_add(panel.append_log, str(e))
            success = False

        if panel.cancelled:
            GLib.idle_add(self._finish_install, browser_label)
            return

        if success:
            self._post_install_set_default(browser)
            GLib.idle_add(self._finish_install, browser_label)
        else:
            GLib.idle_add(panel.set_error, browser_label)

    @staticmethod
    def _read_process_output(
        proc: subprocess.Popen[bytes], panel: InstallPanel
    ) -> None:
        """Read subprocess output byte-by-byte, dispatching lines to the panel."""
        assert proc.stdout is not None
        buf = b""
        fd = proc.stdout.fileno()
        stall_notified = False

        while True:
            ready, _w, _x = select.select([fd], [], [], 5.0)
            if not ready:
                if not stall_notified:
                    stall_notified = True
                    GLib.idle_add(panel.append_log, _("Still working…"))
                continue
            stall_notified = False
            chunk = os.read(fd, 4096)
            if not chunk:
                if buf:
                    line = buf.decode("utf-8", errors="replace")
                    if not line.startswith("STATUS:"):
                        GLib.idle_add(panel.append_log, line)
                break
            if panel.cancelled:
                proc.terminate()
                break
            buf += chunk
            buf = _flush_line_buffer(buf, panel)

    def _post_install_set_default(self, browser: dict) -> None:
        """Set the newly installed browser as default."""
        for variant in browser.get("variants", []):
            if os.path.exists(variant.get("check", "")):
                desktop = variant.get("desktop", "")
                if desktop:
                    self._run_browser_script(["setBrowser", desktop])
                break

    def _finish_install(self, _browser_label: str) -> None:
        """Called when user clicks Done on the install panel."""
        self._set_nav_sensitive(True)
        self.browser_stack.set_visible_child_name("browsers")
        self.refresh_browser_states()

    def _set_nav_sensitive(self, sensitive: bool) -> None:
        """Enable or disable navigation buttons during installation."""
        self.back_btn.set_sensitive(sensitive)
        self.next_btn.set_sensitive(sensitive)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _build_nav(self, parent: Gtk.Box) -> None:
        bar = Gtk.CenterBox()
        bar.add_css_class("bottom-bar")
        parent.append(bar)

        self.startup_check = Gtk.CheckButton(label=_("Show on startup"))
        self.startup_check.add_css_class("startup-check")
        self.startup_check.set_active(self._is_startup_enabled())
        self.startup_check.connect("toggled", self._on_startup_toggled)
        bar.set_start_widget(self.startup_check)

        # Collect page titles for progress dots
        page_titles = [_("Welcome")]
        if self.pages_data:
            for p in self.pages_data:
                page_titles.append(_(p.get("title", "")))

        total = 1 + (len(self.pages_data) if self.pages_data else 0)
        self.progress = ProgressDots(total, page_titles)
        bar.set_center_widget(self.progress)

        nav = Gtk.Box(spacing=10)
        bar.set_end_widget(nav)

        self.back_btn = Gtk.Button()
        back_icon = Gtk.Image.new_from_icon_name("go-previous-symbolic")
        back_icon.set_pixel_size(16)
        self.back_btn.set_child(back_icon)
        self.back_btn.add_css_class("nav-button")
        self.back_btn.add_css_class("back")
        self.back_btn.set_visible(False)
        # Accessibility
        self.back_btn.update_property(
            [Gtk.AccessibleProperty.LABEL], [_("Previous page")]
        )
        self.back_btn.connect("clicked", self._on_back)
        nav.append(self.back_btn)

        self.next_btn = Gtk.Button()
        next_icon = Gtk.Image.new_from_icon_name("go-next-symbolic")
        next_icon.set_pixel_size(16)
        self.next_btn.set_child(next_icon)
        self.next_btn.add_css_class("nav-button")
        self.next_btn.add_css_class("next")
        # Accessibility
        self.next_btn.update_property([Gtk.AccessibleProperty.LABEL], [_("Next page")])
        self.next_btn.connect("clicked", self._on_next)
        nav.append(self.next_btn)

    def _update_nav(self) -> None:
        is_first = self.current_page == 0
        is_last = self.current_page == len(self.page_widgets) - 1

        self.back_btn.set_visible(not is_first)

        if is_last:
            self.next_btn.remove_css_class("nav-button")
            self.next_btn.remove_css_class("next")
            self.next_btn.add_css_class("finish-button")
            self.next_btn.set_child(Gtk.Label(label=_("Get Started")))
            self.next_btn.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Get Started")]
            )
        else:
            self.next_btn.add_css_class("nav-button")
            self.next_btn.add_css_class("next")
            self.next_btn.remove_css_class("finish-button")
            icon = Gtk.Image.new_from_icon_name("go-next-symbolic")
            icon.set_pixel_size(16)
            self.next_btn.set_child(icon)
            self.next_btn.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Next page")]
            )

    def _on_back(self, _btn: Gtk.Button) -> None:
        if self.current_page > 0:
            self.current_page -= 1
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_RIGHT)
            self._navigate()

    def _on_next(self, _btn: Gtk.Button) -> None:
        if self.current_page < len(self.page_widgets) - 1:
            self.current_page += 1
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
            self._navigate()
        else:
            self.close()

    def _navigate(self) -> None:
        if self.current_page == 0:
            self.stack.set_visible_child_name("welcome")
        else:
            self.stack.set_visible_child_name(f"page_{self.current_page - 1}")

        self.progress.set_page(self.current_page)
        self._update_nav()

    # ------------------------------------------------------------------
    # Startup service
    # ------------------------------------------------------------------

    def _is_startup_enabled(self) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", "biglinux-welcome.service"],
                capture_output=True,
                text=True,
            )
            # "masked" means user disabled it; "enabled" means active
            return result.stdout.strip() != "masked"
        except OSError:
            return False

    def _on_startup_toggled(self, btn: Gtk.CheckButton) -> None:
        # Use mask/unmask to override the global enable set by post_install
        action = "unmask" if btn.get_active() else "mask"
        try:
            subprocess.run(
                ["systemctl", "--user", action, "biglinux-welcome.service"],
                capture_output=True,
            )
        except OSError as e:
            print(f"Error toggling autostart: {e}")
