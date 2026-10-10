"""Regression tests for pages.yaml, bundled images and translations."""

import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar

import yaml

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "usr" / "share" / "biglinux" / "welcome"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT))

import install_backend

PAGES = yaml.safe_load((APP_DIR / "pages.yaml").read_text(encoding="utf-8"))


def page(title):
    return next(p for p in PAGES if p["title"] == title)


def all_actions():
    return [a for p in PAGES for a in p.get("actions", [])]


class TestHardwarePage(unittest.TestCase):
    def setUp(self):
        self.page = page("Driver Installation and Hardware Information")
        self.labels = [a["label"] for a in self.page["actions"]]

    def test_single_hardware_management_entry(self):
        entry = next(
            a for a in self.page["actions"] if a["label"] == "Hardware Management"
        )
        self.assertEqual(entry["command"], "big-driver-manager")
        self.assertEqual(entry["package"], "biglinux-driver-manager")
        self.assertTrue(install_backend.is_allowed_package(entry["package"]))

    def test_old_entries_removed(self):
        self.assertNotIn("Driver Manager", self.labels)
        self.assertNotIn("Kernel Manager", self.labels)

    def test_other_tools_preserved(self):
        for label in ("BigLinux Info", "Network Info", "Printers"):
            self.assertIn(label, self.labels)

    def test_no_obsolete_commands_anywhere(self):
        commands = " ".join(a.get("command", "") for a in all_actions())
        self.assertNotIn("big-kernel-manager", commands)
        self.assertNotIn("big-microphone-noise-reduction", commands)
        self.assertNotIn("tts-config", commands)


class TestNoiseReduction(unittest.TestCase):
    def test_uses_current_executable(self):
        discover = page("Discover some features")
        entry = next(a for a in discover["actions"] if a["label"] == "Noise Reduction")
        # big-microphone-noise-reduction no longer exists
        self.assertEqual(entry["command"], "biglinux-microphone")
        self.assertEqual(entry["package"], "biglinux-noise-reduction-pipewire")
        self.assertTrue(install_backend.is_allowed_package(entry["package"]))


class TestTextNarrator(unittest.TestCase):
    def test_text_narrator_entry(self):
        discover = page("Discover some features")
        entry = next(a for a in discover["actions"] if a["label"] == "Text Narrator")
        self.assertEqual(entry["command"], "biglinux-tts")
        self.assertEqual(entry["package"], "tts-biglinux")
        self.assertNotIn("Configure voice", [a["label"] for a in discover["actions"]])


class TestApplicationsPage(unittest.TestCase):
    EXPECTED: ClassVar[dict] = {
        "Big Game Mode": ("bigame-mode", "bigame-ui"),
        "Big Remote Play": ("big-remote-play", "big-remote-play"),
        "BigCam": ("bigcam", "bigcam"),
        "BigLinux Body Tracker": ("biglinux-body-tracker", "big-head-tracker"),
        "Big Advogados": ("big-advogados", "big-advogados"),
    }

    def setUp(self):
        self.titles = [p["title"] for p in PAGES]
        self.page = page("Applications to Install")

    def test_position_right_after_discover(self):
        self.assertEqual(
            self.titles.index("Applications to Install"),
            self.titles.index("Discover some features") + 1,
        )

    def test_page_type(self):
        self.assertEqual(self.page["page_type"], "apps")
        self.assertTrue(self.page["subtitle"])

    def test_six_apps_with_name_icon_description(self):
        apps = self.page["actions"]
        self.assertEqual(len(apps), 6)
        for app in apps:
            self.assertTrue(app["label"])
            self.assertTrue(app["description"])
            self.assertTrue((APP_DIR / "image" / app["icon"]).is_file(), app["icon"])

    def test_packages_and_commands(self):
        apps = {a["label"]: a for a in self.page["actions"]}
        for label, (package, command) in self.EXPECTED.items():
            self.assertEqual(apps[label]["package"], package)
            self.assertEqual(apps[label]["command"], command)
            self.assertTrue(install_backend.is_allowed_package(package))

    def test_body_tracker_never_from_testing(self):
        tracker = next(
            a for a in self.page["actions"] if a["label"] == "BigLinux Body Tracker"
        )
        self.assertEqual(tracker["repository"], "biglinux-stable")
        self.assertEqual(
            install_backend.install_target(tracker["package"], tracker["repository"]),
            "biglinux-stable/biglinux-body-tracker",
        )

    def test_chatai_is_a_pinned_plasmoid(self):
        chatai = next(a for a in self.page["actions"] if a["label"] == "ChatAI")
        self.assertNotIn("package", chatai)
        self.assertIn(chatai["plasmoid"], install_backend.PLASMOID_SOURCES)


class TestBrowsers(unittest.TestCase):
    def test_installable_browsers_are_allowlisted_or_unavailable(self):
        browsers = page("Choose your default browser")["actions"]
        aur_only = {"google-chrome", "opera", "microsoft-edge-stable-bin"}
        for browser in browsers:
            package = browser["package"]
            self.assertTrue(install_backend.is_valid_package_name(package), package)
            if package not in aur_only:
                self.assertTrue(install_backend.is_allowed_package(package), package)

    def test_browser_icons_exist(self):
        for browser in page("Choose your default browser")["actions"]:
            icon = browser.get("icon") or browser["package"]
            self.assertTrue(
                (APP_DIR / "image" / "browsers" / f"{icon}.svg").is_file(), icon
            )


class TestImages(unittest.TestCase):
    def test_every_referenced_icon_exists(self):
        for action in all_actions():
            icon = action.get("icon", "")
            if icon.endswith((".svg", ".png")):
                self.assertTrue((APP_DIR / "image" / icon).is_file(), icon)

    def test_no_unreferenced_images_in_page_folders(self):
        referenced = {a.get("icon") for a in all_actions()}
        for folder in ("applications", "driverAndHardware", "discover"):
            for image in (APP_DIR / "image" / folder).iterdir():
                self.assertIn(f"{folder}/{image.name}", referenced, image)


class TestTranslations(unittest.TestCase):
    def test_translatable_strings_up_to_date(self):
        from generate_strings import extract_strings_from_data

        generated = (APP_DIR / "translatable_strings.py").read_text(encoding="utf-8")
        for string in extract_strings_from_data(PAGES):
            self.assertIn(f"_({string!r})", generated)

    def test_pot_contains_every_yaml_string(self):
        pot = (ROOT / "locale" / "biglinux-welcome.pot").read_text(encoding="utf-8")
        for key in ("Applications to Install", "Hardware Management", "Text Narrator"):
            self.assertIn(f'msgid "{key}"', pot)

    def test_catalogs_compile(self):
        for po in sorted((ROOT / "locale").glob("*.po")):
            result = subprocess.run(
                ["msgfmt", "--check", "-o", "/dev/null", str(po)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, f"{po.name}: {result.stderr}")

    def test_catalogs_fully_translated(self):
        for po in sorted((ROOT / "locale").glob("*.po")):
            result = subprocess.run(
                ["msgattrib", "--untranslated", "--no-obsolete", str(po)],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(
                result.stdout.strip(), "", f"{po.name} has untranslated strings"
            )

    def test_brazilian_portuguese_terms(self):
        import gettext

        mo = (
            APP_DIR.parent.parent
            / "locale"
            / "pt_BR"
            / "LC_MESSAGES"
            / "biglinux-welcome.mo"
        )
        with open(mo, "rb") as f:
            t = gettext.GNUTranslations(f)
        self.assertEqual(t.gettext("Hardware Management"), "Gerenciamento de Hardware")
        self.assertEqual(t.gettext("Text Narrator"), "Narrador de Texto")
        self.assertEqual(t.gettext("Applications to Install"), "Opções para Instalar")
        self.assertEqual(t.gettext("Installation failed"), "Falha na instalação")


class TestPackaging(unittest.TestCase):
    def test_polkit_policy_points_at_helper(self):
        policy = (
            ROOT / "usr/share/polkit-1/actions/org.biglinux.welcome.policy"
        ).read_text()
        self.assertIn("/usr/share/biglinux/welcome/scripts/package-install.sh", policy)
        self.assertIn("auth_admin", policy)
        self.assertNotIn("<allow_active>yes</allow_active>", policy)

    def test_helper_is_executable(self):
        helper = APP_DIR / "scripts" / "package-install.sh"
        self.assertTrue(helper.stat().st_mode & 0o111)

    def test_browser_script_no_longer_installs(self):
        self.assertFalse((APP_DIR / "scripts" / "browserInstall.sh").exists())
        script = (APP_DIR / "scripts" / "browser.sh").read_text()
        self.assertNotIn("pkexec", script)
        self.assertNotIn("pacman", script)


if __name__ == "__main__":
    unittest.main()
