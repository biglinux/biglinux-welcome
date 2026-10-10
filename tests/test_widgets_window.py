"""Tests for BigLinux Welcome — widgets and window logic."""

import sys
import unittest
from pathlib import Path

APP_DIR = str(
    Path(__file__).resolve().parent.parent / "usr" / "share" / "biglinux" / "welcome"
)
sys.path.insert(0, APP_DIR)


class TestGetLineTag(unittest.TestCase):
    """Tests for InstallPanel._get_line_tag static method."""

    @classmethod
    def setUpClass(cls):
        from widgets import InstallPanel

        cls._InstallPanel = InstallPanel

    def tag(self, line):
        return self._InstallPanel._get_line_tag(line)

    def test_error_keyword(self):
        self.assertEqual(self.tag("error: could not open file"), "error")
        self.assertEqual(self.tag("transaction failed"), "error")

    def test_success_keyword(self):
        self.assertEqual(self.tag("Done."), "success")
        self.assertEqual(self.tag("installed successfully"), "success")

    def test_warning_keyword(self):
        self.assertEqual(self.tag("warning: dependency cycle"), "warning")

    def test_info_lines(self):
        self.assertEqual(self.tag("installing firefox..."), "info")
        self.assertEqual(self.tag("removing old package..."), "info")
        self.assertEqual(self.tag("checking keyring..."), "info")
        self.assertEqual(self.tag("resolving dependencies..."), "info")
        self.assertEqual(self.tag(":: Synchronizing package databases..."), "info")

    def test_dim_lines(self):
        self.assertEqual(self.tag("Packages (3): "), "dim")
        self.assertEqual(self.tag("Total Installed Size: 300 MiB"), "dim")
        self.assertEqual(self.tag("Optional dependencies for firefox"), "dim")

    def test_normal_line(self):
        self.assertIsNone(self.tag("some random output"))

    def test_empty_line(self):
        self.assertIsNone(self.tag(""))


# Milestones and phase labels are tested on install_backend.ProgressParser in
# tests/test_install_backend.py::TestProgressParser.
# Line-buffer splitting moved to install_backend.split_output_lines — see
# tests/test_install_backend.py::TestSplitOutputLines.


if __name__ == "__main__":
    unittest.main()
