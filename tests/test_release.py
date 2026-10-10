"""Release consistency: version, packaging, localization and fallback."""

import gettext
import re
import subprocess
import sys
import unittest
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parent.parent
APP_DIR = ROOT / "usr" / "share" / "biglinux" / "welcome"
MO_DIR = ROOT / "usr" / "share" / "locale"
sys.path.insert(0, str(APP_DIR))

from utils import APP_DEVELOPERS, APP_VERSION

PKGBUILD = (ROOT / "pkgbuild" / "PKGBUILD").read_text(encoding="utf-8")


def pkgbuild_var(name):
    return re.search(rf"^{name}=(.+)$", PKGBUILD, re.MULTILINE).group(1).strip("'\"")


class TestVersion(unittest.TestCase):
    def test_version_is_3_0_0(self):
        self.assertEqual(APP_VERSION, "3.0.0")

    def test_pkgbuild_matches_app(self):
        self.assertEqual(pkgbuild_var("pkgver"), APP_VERSION)
        self.assertEqual(pkgbuild_var("pkgrel"), "1")

    def test_epoch_upgrades_date_based_versions(self):
        epoch = pkgbuild_var("epoch")
        new = f"{epoch}:{APP_VERSION}-1"
        old = "26.10.10-0348"  # last date-based build
        try:
            result = subprocess.run(
                ["vercmp", new, old], capture_output=True, text=True, check=False
            )
        except FileNotFoundError:
            self.skipTest("vercmp (pacman) not available")
        self.assertEqual(result.stdout.strip(), "1")

    def test_cli_version(self):
        out = subprocess.run(
            [sys.executable, str(APP_DIR / "main.py"), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
        self.assertEqual(out.strip(), f"BigLinux Welcome {APP_VERSION}")

    def test_authors(self):
        self.assertEqual(
            APP_DEVELOPERS, ["Rafael Ruscher", "Bruno Gonçalves", "Barnabé Di Kartola"]
        )
        for name in ("Rafael Ruscher", "Bruno Goncalves", "Barnabé Di Kartola"):
            self.assertIn(f"# Maintainer: {name}", PKGBUILD)


class TestLocalization(unittest.TestCase):
    """The compiled catalogs translate the visible strings."""

    EXPECTED: ClassVar[dict] = {
        "pt_BR": {
            "Applications to Install": "Opções para Instalar",
            "Hardware Management": "Gerenciamento de Hardware",
            "Text Narrator": "Narrador de Texto",
            "Install": "Instalar",
            "About BigLinux Welcome": "Sobre o BigLinux Welcome",
        },
        "es": {
            "Install": "Instalar",
            "About BigLinux Welcome": "Acerca de BigLinux Welcome",
        },
        "de": {
            "About BigLinux Welcome": "Info zu BigLinux Welcome",
            "Main Menu": "Hauptmenü",
        },
        "en": {"Install": "Install", "Hardware Management": "Hardware Management"},
    }

    def translation(self, language):
        return gettext.translation(
            "biglinux-welcome", str(MO_DIR), languages=[language], fallback=True
        )

    def test_languages(self):
        for language, strings in self.EXPECTED.items():
            t = self.translation(language)
            for source, expected in strings.items():
                self.assertEqual(t.gettext(source), expected, (language, source))

    def test_plural_forms(self):
        t = self.translation("pt_BR")
        singular = "%(count)d package will be downloaded from the configured repositories (%(size)s)."
        plural = "%(count)d packages will be downloaded from the configured repositories (%(size)s)."
        self.assertIn("pacote será", t.ngettext(singular, plural, 1))
        self.assertIn("pacotes serão", t.ngettext(singular, plural, 3))

    def test_unknown_language_falls_back_to_english(self):
        t = self.translation("xx")
        self.assertEqual(
            t.gettext("Applications to Install"), "Applications to Install"
        )

    def test_every_catalog_is_compiled_and_current(self):
        for po in sorted((ROOT / "locale").glob("*.po")):
            mo = MO_DIR / po.stem / "LC_MESSAGES" / "biglinux-welcome.mo"
            self.assertTrue(mo.is_file(), mo)
            with open(mo, "rb") as f:
                catalog = gettext.GNUTranslations(f)
            self.assertNotEqual(catalog.gettext("About BigLinux Welcome"), "", po.stem)


class TestPackagingFiles(unittest.TestCase):
    def test_desktop_file_valid(self):
        desktop = ROOT / "usr/share/applications/org.biglinux.welcome.desktop"
        try:
            result = subprocess.run(
                ["desktop-file-validate", str(desktop)],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            self.skipTest("desktop-file-validate not available")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_no_development_leftovers_tracked(self):
        try:
            files = subprocess.run(
                ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.splitlines()
        except (FileNotFoundError, subprocess.CalledProcessError):
            self.skipTest("not a git checkout")
        leftovers = [
            f
            for f in files
            if f.endswith((".pyc", ".bak", ".old", ".orig", ".tmp", ".log", "~"))
            or "__pycache__/" in f
        ]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
