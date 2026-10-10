"""GUI-level tests: widgets are built (never shown) and driven directly.

Skipped automatically when no display is available."""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = (
    Path(__file__).resolve().parent.parent / "usr" / "share" / "biglinux" / "welcome"
)
sys.path.insert(0, str(APP_DIR))

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")
from gi.repository import Adw, Gdk, GLib, Gtk

# Gtk.init_check() can succeed without any display (e.g. in CI containers)
HAS_DISPLAY = Gtk.init_check() and Gdk.Display.get_default() is not None
if HAS_DISPLAY:
    Adw.init()

import install_backend
from install_backend import Failure, InstallJob, InstallManager, JobState


class FakeJob(InstallJob):
    """Job that emits a scripted run without touching the system."""

    def __init__(self, result=JobState.SUCCEEDED, failure=Failure.NONE):
        super().__init__("Fake")
        self.result = (result, failure)

    def _run(self):
        self._progress(0.2, "Downloading packages…")
        self._log("downloading...")
        self._set_cancellable(False)
        self._progress(0.85, "Installing…")
        return self.result


def run_until_finished(job, timeout=10):
    loop = GLib.MainLoop()
    job.connect("finished", lambda _j: GLib.idle_add(loop.quit))
    GLib.timeout_add_seconds(timeout, loop.quit)
    assert InstallManager.get_default().start(job)
    loop.run()


@unittest.skipUnless(HAS_DISPLAY, "no display")
class TestAppCard(unittest.TestCase):
    def setUp(self):
        from apps_page import AppCard, AppEntry, AppInfo, AppStatus

        self.AppInfo, self.AppStatus = AppInfo, AppStatus
        self.card = AppCard(
            AppEntry("BigCam", "Webcams", "applications/bigcam.svg", "bigcam", "bigcam")
        )
        self.plasmoid = AppCard(
            AppEntry(
                "ChatAI", "AI", "applications/chatai.svg", plasmoid="ChatAI-Plasmoid"
            )
        )

    def tearDown(self):
        InstallManager._default = None

    def button(self, card):
        return card._action_btn

    def test_starts_checking_without_action(self):
        self.assertIs(self.card.status, self.AppStatus.CHECKING)
        self.assertFalse(self.button(self.card).get_visible())

    def test_not_installed_offers_install(self):
        self.card.apply_info(
            self.AppInfo(
                self.AppStatus.NOT_INSTALLED, "1-1", "biglinux-stable", "485 KiB"
            )
        )
        self.assertEqual(self.button(self.card).get_label(), "Install")
        self.assertIn("suggested-action", self.button(self.card).get_css_classes())
        self.assertEqual(self.card._status_label.get_label(), "Not installed")
        self.assertEqual(self.card._meta_label.get_label(), "485 KiB · biglinux-stable")

    def test_installed_offers_open_and_badge(self):
        self.card.apply_info(
            self.AppInfo(self.AppStatus.INSTALLED, repository="biglinux-stable")
        )
        self.assertEqual(self.button(self.card).get_label(), "Open")
        self.assertTrue(self.card._badge.get_visible())
        self.assertIn("installed", self.card._status_label.get_css_classes())

    def test_unavailable_has_no_action(self):
        self.card.apply_info(self.AppInfo(self.AppStatus.UNAVAILABLE))
        self.assertFalse(self.button(self.card).get_visible())
        self.assertEqual(self.card._status_label.get_label(), "Unavailable")

    def test_plasmoid_add_to_panel_states(self):
        self.plasmoid.apply_info(self.AppInfo(self.AppStatus.INSTALLED, in_panel=False))
        self.assertEqual(self.button(self.plasmoid).get_label(), "Add to Panel")
        self.assertTrue(self.button(self.plasmoid).get_sensitive())
        self.plasmoid.apply_info(self.AppInfo(self.AppStatus.INSTALLED, in_panel=True))
        self.assertEqual(self.button(self.plasmoid).get_label(), "Added to Panel")
        self.assertFalse(self.button(self.plasmoid).get_sensitive())

    def test_unsupported_desktop(self):
        self.plasmoid.apply_info(self.AppInfo(self.AppStatus.UNSUPPORTED))
        self.assertEqual(self.plasmoid._status_label.get_label(), "Requires KDE Plasma")
        self.assertFalse(self.button(self.plasmoid).get_visible())

    def test_successful_job_updates_card(self):
        self.card.apply_info(self.AppInfo(self.AppStatus.NOT_INSTALLED))
        job = FakeJob()
        self.card.bind_job(job)
        self.assertIs(self.card.status, self.AppStatus.INSTALLING)
        self.assertEqual(self.card._footer.get_visible_child_name(), "progress")
        run_until_finished(job)
        self.assertIs(self.card.status, self.AppStatus.INSTALLED)
        self.assertEqual(self.button(self.card).get_label(), "Open")

    def test_refresh_does_not_interrupt_running_install(self):
        job = FakeJob()
        self.card.bind_job(job)
        self.card.apply_info(self.AppInfo(self.AppStatus.NOT_INSTALLED))
        self.assertIs(self.card.status, self.AppStatus.INSTALLING)

    def test_failed_job_shows_reason_and_retry(self):
        job = FakeJob(JobState.FAILED, Failure.NETWORK)
        self.card.bind_job(job)
        run_until_finished(job)
        self.assertIs(self.card.status, self.AppStatus.FAILED)
        self.assertEqual(self.button(self.card).get_label(), "Try Again")
        self.assertEqual(
            self.card._error_label.get_label(),
            install_backend.failure_message(Failure.NETWORK),
        )
        self.assertTrue(self.card._details_btn.get_visible())

    def test_outdated_database_offers_full_update(self):
        job = FakeJob(JobState.FAILED, Failure.OUTDATED_DATABASE)
        self.card.bind_job(job)
        run_until_finished(job)
        self.assertEqual(self.button(self.card).get_label(), "Update and Install")

    def test_auth_cancel_returns_to_not_installed(self):
        job = FakeJob(JobState.AUTH_CANCELLED)
        self.card.bind_job(job)
        run_until_finished(job)
        self.assertIs(self.card.status, self.AppStatus.NOT_INSTALLED)

    def test_other_cards_locked_while_installing(self):
        self.plasmoid.apply_info(self.AppInfo(self.AppStatus.NOT_INSTALLED))
        job = FakeJob()
        loop = GLib.MainLoop()
        job.connect("finished", lambda _j: GLib.idle_add(loop.quit))
        InstallManager.get_default().start(job)
        self.assertFalse(self.button(self.plasmoid).get_sensitive())
        GLib.timeout_add_seconds(10, loop.quit)
        loop.run()
        self.assertTrue(self.button(self.plasmoid).get_sensitive())


@unittest.skipUnless(HAS_DISPLAY, "no display")
class TestInstallPanel(unittest.TestCase):
    def tearDown(self):
        InstallManager._default = None

    def test_binding_replays_log_and_shows_success(self):
        from widgets import InstallPanel

        job = FakeJob()
        run_until_finished(job)
        panel = InstallPanel("BigCam", "applications/bigcam.svg")
        panel.bind_job(job)
        buffer = panel._log_buffer
        text = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        self.assertIn("downloading...", text)
        self.assertEqual(panel._title.get_label(), "BigCam installed successfully!")
        self.assertTrue(panel._done_btn.get_visible())

    def test_error_state(self):
        from widgets import InstallPanel

        job = FakeJob(JobState.FAILED, Failure.DISK_SPACE)
        run_until_finished(job)
        panel = InstallPanel("BigCam", None)
        panel.bind_job(job)
        self.assertEqual(
            panel._subtitle.get_label(),
            install_backend.failure_message(Failure.DISK_SPACE),
        )
        self.assertTrue(panel._revealer.get_reveal_child())


class TestCheckApps(unittest.TestCase):
    """State detection logic, with the system queries replaced."""

    def test_statuses(self):
        from apps_page import AppEntry, AppStatus, check_apps

        entries = [
            AppEntry("A", package="bigcam"),
            AppEntry("B", package="bigame-mode"),
            AppEntry("C", package="biglinux-body-tracker"),
            AppEntry("D", plasmoid="ChatAI-Plasmoid"),
        ]
        repo = {
            "bigame-mode": install_backend.RepoPackage(
                "bigame-mode", "2", "biglinux-stable", 7 * 1024**2
            ),
        }
        with (
            patch("apps_page.installed_packages", return_value={"bigcam"}),
            patch("apps_page.repo_packages", return_value=repo),
            patch("apps_page.is_plasma_session", return_value=True),
            patch("apps_page.is_plasmoid_installed", return_value=False),
        ):
            result = check_apps(entries)
        self.assertIs(result["A"].status, AppStatus.INSTALLED)
        self.assertIs(result["B"].status, AppStatus.NOT_INSTALLED)
        self.assertEqual(
            result["B"].download_size, install_backend.format_size(7 * 1024**2)
        )
        self.assertIs(result["C"].status, AppStatus.UNAVAILABLE)
        self.assertIs(result["D"].status, AppStatus.NOT_INSTALLED)

    def test_pinned_repository_is_used_for_availability(self):
        from apps_page import AppEntry, AppStatus, check_apps

        testing = install_backend.RepoPackage(
            "biglinux-body-tracker", "24.11", "biglinux-testing", 1
        )
        stable = install_backend.RepoPackage(
            "biglinux-body-tracker", "24.10", "biglinux-stable", 2
        )
        repo = {
            "biglinux-body-tracker": testing,
            "biglinux-testing/biglinux-body-tracker": testing,
            "biglinux-stable/biglinux-body-tracker": stable,
        }
        entry = AppEntry(
            "T", package="biglinux-body-tracker", repository="biglinux-stable"
        )
        with (
            patch("apps_page.installed_packages", return_value=set()),
            patch("apps_page.repo_packages", return_value=repo) as query,
        ):
            result = check_apps([entry])
        query.assert_called_once_with({"biglinux-stable/biglinux-body-tracker"})
        self.assertIs(result["T"].status, AppStatus.NOT_INSTALLED)
        self.assertEqual(result["T"].repository, "biglinux-stable")
        self.assertEqual(result["T"].version, "24.10")

    def test_plasmoid_unsupported_outside_plasma(self):
        from apps_page import AppEntry, AppStatus, check_apps

        with (
            patch("apps_page.is_plasma_session", return_value=False),
            patch("apps_page.installed_packages", return_value=set()),
            patch("apps_page.repo_packages", return_value={}),
        ):
            result = check_apps([AppEntry("D", plasmoid="ChatAI-Plasmoid")])
        self.assertIs(result["D"].status, AppStatus.UNSUPPORTED)


@unittest.skipUnless(HAS_DISPLAY, "no display")
class TestWindow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from gi.repository import Gio

        cls.app = Adw.Application(
            application_id="org.biglinux.welcome.tests",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )
        cls.app.register(None)

    def setUp(self):
        from window import WelcomeWindow

        with patch("window.WelcomeWindow._is_startup_enabled", return_value=True):
            self.win = WelcomeWindow(self.app)
        # GTK on Wayland crashes destroying a never-realized application
        # window; the real app always presents it first
        self.win.realize()

    def tearDown(self):
        self.win.destroy()
        InstallManager._default = None

    def test_all_pages_built_in_order(self):
        from apps_page import AppsPage

        titles = [p["title"] for p in self.win.pages_data]
        self.assertEqual(len(self.win.page_widgets), len(titles) + 1)
        apps_index = titles.index("Applications to Install") + 1
        self.assertIsInstance(self.win._page(apps_index), AppsPage)
        self.assertEqual(apps_index, titles.index("Discover some features") + 2)

    def test_pages_are_built_on_demand(self):
        # Only the visible page exists after startup
        self.assertIsNotNone(self.win.page_widgets[0])
        self.assertTrue(all(p is None for p in self.win.page_widgets[2:]))
        self.win._prepare_next_page()
        self.assertIsNotNone(self.win.page_widgets[1])
        self.assertIs(self.win._page(1), self.win.page_widgets[1])

    def test_navigation_through_every_page(self):
        total = len(self.win.page_widgets)
        for expected in range(1, total):
            self.win._on_next(None)
            self.assertEqual(self.win.current_page, expected)
            self.assertIs(
                self.win.stack.get_visible_child(), self.win.page_widgets[expected]
            )
        self.assertEqual(self.win.next_btn.get_child().get_label(), "Get Started")
        for expected in range(total - 2, -1, -1):
            self.win._on_back(None)
            self.assertEqual(self.win.current_page, expected)
        self.assertFalse(self.win.back_btn.get_visible())

    def test_navigation_blocked_while_disabled(self):
        self.win._set_nav_sensitive(False)
        self.win._on_next(None)
        self.assertEqual(self.win.current_page, 0)
        self.win._set_nav_sensitive(True)

    def test_header_has_about_menu(self):
        self.app.activate_action("about", None)  # must not raise without startup
        self.assertIsNotNone(self.win.get_content())

    def test_close_is_confirmed_while_installing(self):
        manager = InstallManager.get_default()
        with (
            patch.object(InstallManager, "busy", new=True),
            patch("window.show_alert") as alert,
        ):
            self.assertTrue(self.win._on_close_request(self.win))
            alert.assert_called_once()
        self.assertFalse(manager.busy)
        self.assertFalse(self.win._on_close_request(self.win))


if __name__ == "__main__":
    unittest.main()


@unittest.skipUnless(HAS_DISPLAY, "no display")
class TestApplication(unittest.TestCase):
    def test_single_window_and_about(self):
        from app import BigLinuxWelcomeApp
        from gi.repository import Gio

        app = BigLinuxWelcomeApp()
        app.set_flags(Gio.ApplicationFlags.NON_UNIQUE)
        seen = {}

        def on_activate(a):
            if "first" not in seen:
                seen["first"] = a.win
                GLib.idle_add(lambda: a.activate() or False)  # second launch
            else:
                seen["windows"] = len(a.get_windows())
                seen["same"] = a.win is seen["first"]
                a.activate_action("about", None)
                GLib.timeout_add(300, lambda: a.quit() or False)

        app.connect_after("activate", on_activate)
        with patch("window.WelcomeWindow._is_startup_enabled", return_value=True):
            app.run([])
        self.assertEqual(seen.get("windows"), 1)
        self.assertTrue(seen.get("same"))
