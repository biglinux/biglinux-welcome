"""Tests for BigLinux Welcome — utility functions."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch

# Add the app directory to sys.path for imports
APP_DIR = str(
    Path(__file__).resolve().parent.parent / "usr" / "share" / "biglinux" / "welcome"
)
sys.path.insert(0, APP_DIR)

# Also add generate_strings.py location
PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, PROJECT_ROOT)


class TestExtractStrings(unittest.TestCase):
    """Tests for generate_strings.extract_strings_from_data."""

    def setUp(self):
        from generate_strings import extract_strings_from_data

        self.extract = extract_strings_from_data

    def test_extracts_title(self):
        data = {"title": "Hello World"}
        result = self.extract(data)
        self.assertEqual(result, {"Hello World"})

    def test_extracts_subtitle(self):
        data = {"subtitle": "Welcome"}
        result = self.extract(data)
        self.assertEqual(result, {"Welcome"})

    def test_extracts_label(self):
        data = {"label": "Click me"}
        result = self.extract(data)
        self.assertEqual(result, {"Click me"})

    def test_ignores_non_translatable_keys(self):
        data = {"command": "echo hello", "type": "app"}
        result = self.extract(data)
        self.assertEqual(result, set())

    def test_extracts_from_nested_structure(self):
        data = [
            {
                "title": "Page One",
                "subtitle": "Description",
                "actions": [
                    {"label": "Action A"},
                    {"label": "Action B"},
                ],
            }
        ]
        result = self.extract(data)
        self.assertEqual(result, {"Page One", "Description", "Action A", "Action B"})

    def test_deduplicates(self):
        data = [{"title": "Same"}, {"title": "Same"}]
        result = self.extract(data)
        self.assertEqual(result, {"Same"})

    def test_empty_data(self):
        result = self.extract({})
        self.assertEqual(result, set())

    def test_none_values_skipped(self):
        data = {"title": None, "label": "Valid"}
        result = self.extract(data)
        self.assertEqual(result, {"Valid"})


class TestParseOsRelease(unittest.TestCase):
    """Tests for utils.parse_os_release."""

    def test_parses_standard_format(self):
        fake_content = 'NAME="BigLinux"\nVERSION="2024"\nPRETTY_NAME="BigLinux 2024"\n'
        with patch("builtins.open", mock_open(read_data=fake_content)):
            with patch("platform.freedesktop_os_release", side_effect=OSError):
                from utils import parse_os_release

                result = parse_os_release()
                self.assertEqual(result["NAME"], "BigLinux")
                self.assertEqual(result["VERSION"], "2024")

    def test_handles_missing_file(self):
        with patch("platform.freedesktop_os_release", side_effect=OSError):
            with patch("builtins.open", side_effect=OSError):
                from utils import parse_os_release

                result = parse_os_release()
                self.assertEqual(result, {})


class TestGetDesktop(unittest.TestCase):
    """Tests for utils.get_desktop."""

    def test_kde(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
            from utils import get_desktop

            self.assertEqual(get_desktop(), "Plasma")

    def test_gnome(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}):
            from utils import get_desktop

            self.assertEqual(get_desktop(), "GNOME")

    def test_unknown(self):
        with patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": ""}):
            from utils import get_desktop

            self.assertEqual(get_desktop(), "Unknown")


class TestGetLogoPath(unittest.TestCase):
    """Tests for utils.get_logo_path."""

    def test_finds_existing_logo(self):
        from utils import get_logo_path

        with patch(
            "os.path.exists",
            side_effect=lambda p: p == "/usr/share/pixmaps/biglinux.svg",
        ):
            result = get_logo_path({"LOGO": "biglinux"})
            self.assertEqual(result, "/usr/share/pixmaps/biglinux.svg")

    def test_returns_none_when_logo_missing(self):
        from utils import get_logo_path

        with patch("os.path.exists", return_value=False):
            result = get_logo_path({"LOGO": "nonexistent"})
            self.assertIsNone(result)

    def test_returns_none_when_no_logo_key(self):
        from utils import get_logo_path

        with patch("os.path.exists", return_value=False):
            result = get_logo_path({})
            self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
