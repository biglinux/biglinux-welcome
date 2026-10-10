"""BigLinux Welcome — Main window."""

from __future__ import annotations

import gettext
import os
import subprocess
import threading

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from apps_page import AppsPage
from gi.repository import Adw, Gio, GLib, Gtk
from install_backend import InstallJob, InstallManager, JobState, repo_packages
from install_flow import InstallRequest, request_install
from utils import (
    APP_NAME,
    APP_PATH,
    get_logo_path,
    load_icon,
    load_pages,
    parse_os_release,
)
from widgets import (
    ActionCard,
    AnimatedLogo,
    BrowserCard,
    InfoCard,
    InstallPanel,
    ProgressDots,
    card_grid,
    command_available,
    launch_command,
    make_heading,
    show_alert,
)

_ = gettext.gettext

# Uniform launcher card width; grids wrap on narrow windows
ACTION_CARD_WIDTH = 150
CARD_SPACING = 14


class WelcomeWindow(Adw.ApplicationWindow):
    """Main welcome window."""

    def __init__(self, app: Adw.Application, start_page: int = 0) -> None:
        super().__init__(application=app)
        self.set_default_size(1000, 780)
        self.set_size_request(360, 480)
        self.set_title(APP_NAME)

        self.pages_data = load_pages(os.path.join(APP_PATH, "pages.yaml"))

        # Determine the actual starting page index to avoid out-of-bounds errors
        total_pages = 1 + len(self.pages_data)
        self.current_page = max(0, min(start_page, total_pages - 1))

        # Pages are built on first use (see _page); None = not built yet
        self.page_widgets: list[Gtk.Widget | None] = [None] * total_pages
        self.browser_cards: list[BrowserCard] = []
        self._install_panel: InstallPanel | None = None
        self._close_confirmed = False

        self._build_ui()
        self._setup_shortcuts()
        self.connect("close-request", self._on_close_request)
        self._navigate()

    # ------------------------------------------------------------------
    # UI Construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self.toast_overlay = Adw.ToastOverlay()
        self.set_content(self.toast_overlay)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.toast_overlay.set_child(main)

        header = Adw.HeaderBar()
        header.add_css_class("flat")
        header.set_show_title(False)
        main.append(header)

        menu = Gio.Menu()
        menu.append(_("About BigLinux Welcome"), "app.about")
        menu_button = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_button.set_tooltip_text(_("Main Menu"))
        menu_button.update_property([Gtk.AccessibleProperty.LABEL], [_("Main Menu")])
        header.pack_end(menu_button)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(320)
        self.stack.set_vexpand(True)
        main.append(self.stack)

        self._build_nav(main)

    def add_toast(self, message: str) -> None:
        """Show a short, non-blocking notification."""
        toast = Adw.Toast(title=message)
        toast.set_timeout(4)
        self.toast_overlay.add_toast(toast)

    def _page(self, index: int) -> Gtk.Widget:
        """Return page index, building it on first use.

        Only the visible page is built at startup; the next one is prepared
        while idle, so the first frame appears sooner and pages the user
        never opens cost nothing (no widgets, no package queries)."""
        page = self.page_widgets[index]
        if page is not None:
            return page
        if index == 0:
            page = self._build_welcome()
        else:
            data = self.pages_data[index - 1]
            page_type = data.get("page_type")
            if page_type == "browsers":
                page = self._build_browser_page(data)
            elif page_type == "apps":
                page = AppsPage(data)
            else:
                page = self._build_action_page(data)
        self.stack.add_named(page, f"page_{index}")
        self.page_widgets[index] = page
        return page

    def _prepare_next_page(self) -> bool:
        if self.current_page + 1 < len(self.page_widgets):
            self._page(self.current_page + 1)
        return GLib.SOURCE_REMOVE

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
            logo = load_icon(logo_path, 130)
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
            logo.update_property([Gtk.AccessibleProperty.LABEL], [distro])
        else:
            main.append(make_heading(distro, "hero-title"))
            subtitle_text = _("Welcome to your new system")

        # Subtitle
        subtitle = Gtk.Label(label=subtitle_text)
        subtitle.add_css_class("hero-subtitle")
        subtitle.set_wrap(True)
        subtitle.set_justify(Gtk.Justification.CENTER)
        main.append(subtitle)

        # Version badge
        version = os_info.get("VERSION", "")
        if version:
            badge = Gtk.Label(label=f"v{version}")
            badge.add_css_class("hero-version")
            badge.set_halign(Gtk.Align.CENTER)
            main.append(badge)

        # Spacer
        spacer = Gtk.Box()
        spacer.set_size_request(-1, 10)
        main.append(spacer)

        # Info card
        main.append(InfoCard())

        return scroll

    def _build_page_header(self, data: dict, max_chars: int = 60) -> Gtk.Box:
        # The box fills; the labels center themselves (see make_heading)
        header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        header.append(make_heading(_(data.get("title", "")), "page-title"))

        subtitle = data.get("subtitle", "")
        if subtitle:
            sub = Gtk.Label(label=_(subtitle))
            sub.set_halign(Gtk.Align.CENTER)
            sub.add_css_class("page-subtitle")
            sub.set_wrap(True)
            sub.set_max_width_chars(max_chars)
            sub.set_justify(Gtk.Justification.CENTER)
            header.append(sub)
        return header

    def _build_action_page(self, data: dict) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        main.set_margin_top(28)
        main.set_margin_bottom(32)
        main.set_margin_start(24)
        main.set_margin_end(24)
        scroll.set_child(main)
        main.append(self._build_page_header(data))

        cards = []
        for action in data.get("actions", []):
            card = ActionCard(action)
            if "qrcode-card" not in card.get_css_classes():
                card.set_size_request(ACTION_CARD_WIDTH, -1)
            cards.append(card)
        main.append(card_grid(cards, 4, CARD_SPACING))

        return scroll

    def _build_browser_page(self, data: dict) -> Gtk.Widget:
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=26)
        main.set_margin_top(28)
        main.set_margin_bottom(32)
        main.set_margin_start(24)
        main.set_margin_end(24)
        scroll.set_child(main)

        # -- Header (always visible, even during install) --
        main.append(self._build_page_header(data, max_chars=55))

        # -- Inner stack: cards grid ↔ install panel --
        self.browser_stack = Gtk.Stack()
        self.browser_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.browser_stack.set_transition_duration(280)
        self.browser_stack.set_vexpand(True)
        main.append(self.browser_stack)

        self.browser_cards = [
            BrowserCard(browser, self._on_browser_select)
            for browser in data.get("actions", [])
        ]
        grid = card_grid(self.browser_cards, 5, 16)
        grid.set_valign(Gtk.Align.START)

        self.browser_stack.add_named(grid, "browsers")

        # Install panel placeholder (replaced dynamically)
        placeholder = Gtk.Box()
        self.browser_stack.add_named(placeholder, "installing")

        # -- Loading overlay for "set default" --
        self._browser_loading_overlay = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=12
        )
        self._browser_loading_overlay.set_halign(Gtk.Align.FILL)
        self._browser_loading_overlay.set_valign(Gtk.Align.FILL)
        self._browser_loading_overlay.set_visible(False)
        self._browser_loading_overlay.add_css_class("browser-loading-overlay")

        self._browser_loading_spinner = Adw.Spinner()
        self._browser_loading_spinner.set_size_request(48, 48)
        self._browser_loading_spinner.set_vexpand(True)
        self._browser_loading_spinner.set_valign(Gtk.Align.END)
        self._browser_loading_overlay.append(self._browser_loading_spinner)

        self._browser_loading_label = Gtk.Label(label="")
        self._browser_loading_label.add_css_class("page-subtitle")
        self._browser_loading_label.set_vexpand(True)
        self._browser_loading_label.set_valign(Gtk.Align.START)
        self._browser_loading_overlay.append(self._browser_loading_label)
        self._browser_loading_overlay.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [_("Changing default browser")],
        )

        page_overlay = Gtk.Overlay()
        page_overlay.set_child(scroll)
        page_overlay.add_overlay(self._browser_loading_overlay)

        self.refresh_browser_states()
        return page_overlay

    # ------------------------------------------------------------------
    # Browser logic
    # ------------------------------------------------------------------

    def _run_browser_script(self, args: list[str]) -> str:
        script_path = os.path.join(APP_PATH, "scripts", "browser.sh")
        try:
            result = subprocess.run(
                [script_path, *args],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as e:
            print(f"Error running browser script {args}: {e}")
            return ""

    def refresh_browser_states(self) -> bool:
        """Re-check installed browsers, the default one and repository
        availability, in the background."""

        def worker() -> None:
            default = self._run_browser_script(["getBrowser"])
            packages = [c.browser.get("package", "") for c in self.browser_cards]
            available = set(repo_packages([p for p in packages if p]))
            GLib.idle_add(self._apply_browser_states, default, available)

        threading.Thread(target=worker, daemon=True).start()
        return GLib.SOURCE_REMOVE

    def _apply_browser_states(self, default_browser: str, available: set[str]) -> bool:
        for card in self.browser_cards:
            installed_desktop = None
            for variant in card.browser.get("variants", []):
                check_path = variant.get("check", "")
                if check_path and os.path.exists(check_path):
                    installed_desktop = variant.get("desktop", "")
                    break

            is_installed = installed_desktop is not None
            card.set_installed(is_installed)
            card.set_available(card.browser.get("package", "") in available)
            card.detected_desktop = installed_desktop
            card.set_selected(is_installed and installed_desktop == default_browser)
        return GLib.SOURCE_REMOVE

    def _on_browser_select(self, selected_card: BrowserCard) -> None:
        browser = selected_card.browser
        label = browser.get("label", "")

        # If already installed, just set as default (no panel needed)
        if selected_card._check_installed():
            thread = threading.Thread(
                target=self._set_default_browser, args=(selected_card,), daemon=True
            )
            thread.start()
            return

        if selected_card.available is False:
            self._explain_unavailable_browser(label)
            return

        request = InstallRequest(
            label=label,
            icon=f"browsers/{selected_card.icon_name}.svg",
            package=browser.get("package", ""),
        )
        selected_card.set_loading(True)
        request_install(
            selected_card,
            request,
            lambda job: self._show_browser_install(selected_card, job),
            lambda: selected_card.set_loading(False),
        )

    def _explain_unavailable_browser(self, label: str) -> None:
        responses = [("close", _("Close"), Adw.ResponseAppearance.DEFAULT)]
        if command_available("big-store"):
            responses.append(
                ("store", _("Open Big Store"), Adw.ResponseAppearance.SUGGESTED)
            )

        def on_response(response: str) -> None:
            if response == "store":
                try:
                    launch_command("big-store", self)
                except GLib.Error as e:
                    print(f"Could not open Big Store: {e}")

        show_alert(
            self,
            _("%s is not available") % label,
            _(
                "%s is not in the configured repositories, so it cannot be "
                "installed safely from here. You can look for it in Big Store, "
                "which shows where each package comes from."
            )
            % label,
            responses,
            on_response,
        )

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
        self._browser_loading_spinner.set_visible(True)
        for card in self.browser_cards:
            card.set_sensitive(False)

    def _hide_browser_loading(self, browser_label: str = "") -> None:
        self._browser_loading_spinner.set_visible(False)
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

    def _show_browser_install(self, card: BrowserCard, job: InstallJob) -> None:
        """Replace the browser grid with the install panel for job."""
        card.set_loading(False)
        browser = card.browser
        browser_label = browser.get("label", "")

        panel = InstallPanel(browser_label, f"browsers/{card.icon_name}.svg")
        panel.set_done_callback(self._finish_install)
        panel.bind_job(job)
        job.connect("finished", self._on_browser_job_finished, browser, panel)

        old = self.browser_stack.get_child_by_name("installing")
        if old:
            self.browser_stack.remove(old)
        self.browser_stack.add_named(panel, "installing")
        self.browser_stack.set_visible_child_name("installing")
        self._install_panel = panel

        # Keep the user on this page until they acknowledge the result
        self._set_nav_sensitive(False)

    def _on_browser_job_finished(
        self, job: InstallJob, browser: dict, panel: InstallPanel
    ) -> None:
        if job.state is not JobState.SUCCEEDED:
            return
        label = browser.get("label", "")
        panel.set_success(label, _("Setting it as your default browser…"))

        def worker() -> None:
            done = self._post_install_set_default(browser)
            message = (
                _("It has been set as your default browser.")
                if done
                else _("The application is ready to use.")
            )
            GLib.idle_add(panel.set_success, label, message)

        threading.Thread(target=worker, daemon=True).start()

    def _post_install_set_default(self, browser: dict) -> bool:
        """Set the newly installed browser as default (background thread)."""
        for variant in browser.get("variants", []):
            if os.path.exists(variant.get("check", "")):
                desktop = variant.get("desktop", "")
                if desktop:
                    self._run_browser_script(["setBrowser", desktop])
                    return True
                break
        return False

    def _finish_install(self) -> None:
        """Called when user clicks Done on the install panel."""
        self._set_nav_sensitive(True)
        self.browser_stack.set_visible_child_name("browsers")
        self._install_panel = None
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
        page_titles = [_("Welcome")] + [_(p["title"]) for p in self.pages_data]
        self.progress = ProgressDots(len(page_titles), page_titles)
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
        self.back_btn.set_tooltip_text(_("Previous page"))
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
        self.next_btn.set_tooltip_text(_("Next page"))
        # Accessibility
        self.next_btn.update_property([Gtk.AccessibleProperty.LABEL], [_("Next page")])
        self.next_btn.connect("clicked", self._on_next)
        nav.append(self.next_btn)

    def _setup_shortcuts(self) -> None:
        """Alt+Left / Alt+Right move between pages."""
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, callback in (
            ("<Alt>Left", self._on_back),
            ("<Alt>Right", self._on_next_shortcut),
        ):
            controller.add_shortcut(
                Gtk.Shortcut.new(
                    Gtk.ShortcutTrigger.parse_string(accel),
                    Gtk.CallbackAction.new(lambda *_a, cb=callback: cb(None) or True),
                )
            )
        self.add_controller(controller)

    def _on_next_shortcut(self, _btn: Gtk.Button | None) -> None:
        # Never close the window from the keyboard shortcut on the last page
        if self.current_page < len(self.page_widgets) - 1:
            self._on_next(None)

    def _update_nav(self) -> None:
        is_first = self.current_page == 0
        is_last = self.current_page == len(self.page_widgets) - 1

        self.back_btn.set_visible(not is_first)

        if is_last:
            self.next_btn.remove_css_class("nav-button")
            self.next_btn.remove_css_class("next")
            self.next_btn.add_css_class("finish-button")
            self.next_btn.set_child(Gtk.Label(label=_("Get Started")))
            self.next_btn.set_tooltip_text(None)
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
            self.next_btn.set_tooltip_text(_("Next page"))
            self.next_btn.update_property(
                [Gtk.AccessibleProperty.LABEL], [_("Next page")]
            )

    def _on_back(self, _btn: Gtk.Button | None) -> None:
        if not self.back_btn.get_sensitive():
            return
        if self.current_page > 0:
            self.current_page -= 1
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_RIGHT)
            self._navigate()

    def _on_next(self, _btn: Gtk.Button | None) -> None:
        if not self.next_btn.get_sensitive():
            return
        if self.current_page < len(self.page_widgets) - 1:
            self.current_page += 1
            self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
            self._navigate()
        else:
            self.close()

    def _navigate(self) -> None:
        built = self.page_widgets[self.current_page] is not None
        page = self._page(self.current_page)
        self.stack.set_visible_child(page)
        if built and isinstance(page, AppsPage):
            # Apps may have been installed or removed elsewhere meanwhile
            page.refresh()
        # After the transition, so preparing it never delays the animation
        GLib.timeout_add(
            self.stack.get_transition_duration() + 100, self._prepare_next_page
        )

        self.progress.set_page(self.current_page)
        self._update_nav()

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    def _on_close_request(self, _window: Gtk.Window) -> bool:
        if self._close_confirmed or not InstallManager.get_default().busy:
            return False

        def on_response(response: str) -> None:
            if response == "close":
                self._close_confirmed = True
                self.close()

        show_alert(
            self,
            _("An installation is in progress"),
            _(
                "If you close the window now, the installation will continue in "
                "the background, but you will not see its result."
            ),
            [
                ("keep", _("Keep Open"), Adw.ResponseAppearance.DEFAULT),
                ("close", _("Close Anyway"), Adw.ResponseAppearance.DESTRUCTIVE),
            ],
            on_response,
        )
        return True

    # ------------------------------------------------------------------
    # Startup service
    # ------------------------------------------------------------------

    def _is_startup_enabled(self) -> bool:
        try:
            result = subprocess.run(
                ["systemctl", "--user", "is-enabled", "biglinux-welcome.service"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            # "masked" means user disabled it; "enabled" means active
            return result.stdout.strip() != "masked"
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _on_startup_toggled(self, btn: Gtk.CheckButton) -> None:
        # Use mask/unmask to override the global enable set by post_install
        action = "unmask" if btn.get_active() else "mask"
        try:
            subprocess.run(
                ["systemctl", "--user", action, "biglinux-welcome.service"],
                capture_output=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"Error toggling autostart: {e}")
