"""Tests for BigLinux Welcome — widgets and window logic."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

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


class TestMilestones(unittest.TestCase):
    """Tests for InstallPanel milestone matching logic."""

    @classmethod
    def setUpClass(cls):
        from widgets import InstallPanel

        cls.milestones = InstallPanel._MILESTONES

    def test_milestones_are_sorted_by_fraction(self):
        fractions = [f for _, f in self.milestones]
        self.assertEqual(fractions, sorted(fractions))

    def test_all_milestones_between_0_and_1(self):
        for keyword, fraction in self.milestones:
            self.assertGreater(fraction, 0.0, f"Milestone '{keyword}' is <= 0")
            self.assertLessEqual(fraction, 1.0, f"Milestone '{keyword}' is > 1")

    def test_key_milestones_present(self):
        keywords = {k for k, _ in self.milestones}
        self.assertIn("synchronizing", keywords)
        self.assertIn("installing", keywords)
        self.assertIn("running post-transaction hooks", keywords)

    def test_cancel_cutoff_is_a_milestone(self):
        from widgets import InstallPanel

        cutoff = InstallPanel._CANCEL_CUTOFF
        milestone_fractions = {f for _, f in self.milestones}
        self.assertIn(cutoff, milestone_fractions)


class TestPhaseLabels(unittest.TestCase):
    """Tests for InstallPanel._PHASE_LABELS coverage."""

    @classmethod
    def setUpClass(cls):
        from widgets import InstallPanel

        cls.milestones = InstallPanel._MILESTONES
        cls.labels = InstallPanel._PHASE_LABELS

    def test_every_milestone_has_a_label(self):
        for keyword, _ in self.milestones:
            self.assertIn(
                keyword,
                self.labels,
                f"Milestone '{keyword}' missing from _PHASE_LABELS",
            )

    def test_labels_are_nonempty_strings(self):
        for keyword, label in self.labels.items():
            self.assertIsInstance(label, str)
            self.assertTrue(len(label) > 0, f"Empty label for '{keyword}'")


class TestFlushLineBuffer(unittest.TestCase):
    """Tests for window._flush_line_buffer."""

    def setUp(self):
        self.mock_panel = MagicMock()
        self.glib_patcher = patch("window.GLib")
        self.mock_glib = self.glib_patcher.start()
        # Make idle_add just call the function
        self.mock_glib.idle_add = MagicMock()

    def tearDown(self):
        self.glib_patcher.stop()

    def _flush(self, buf):
        from window import _flush_line_buffer

        return _flush_line_buffer(buf, self.mock_panel)

    def test_newline_dispatches_to_append_log(self):
        remainder = self._flush(b"hello world\n")
        self.assertEqual(remainder, b"")
        self.mock_glib.idle_add.assert_called_once_with(
            self.mock_panel.append_log, "hello world"
        )

    def test_cr_dispatches_to_parse_progress(self):
        remainder = self._flush(b"progress 50%\r")
        self.assertEqual(remainder, b"")
        self.mock_glib.idle_add.assert_called_once_with(
            self.mock_panel.parse_progress, "progress 50%"
        )

    def test_status_lines_skipped(self):
        remainder = self._flush(b"STATUS:started\n")
        self.assertEqual(remainder, b"")
        self.mock_glib.idle_add.assert_not_called()

    def test_incomplete_line_kept_in_buffer(self):
        remainder = self._flush(b"partial data without newline")
        self.assertEqual(remainder, b"partial data without newline")
        self.mock_glib.idle_add.assert_not_called()

    def test_multiple_lines(self):
        remainder = self._flush(b"line1\nline2\npartial")
        self.assertEqual(remainder, b"partial")
        calls = self.mock_glib.idle_add.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], call(self.mock_panel.append_log, "line1"))
        self.assertEqual(calls[1], call(self.mock_panel.append_log, "line2"))

    def test_empty_lines_skipped(self):
        remainder = self._flush(b"\n\nhello\n")
        self.assertEqual(remainder, b"")
        calls = self.mock_glib.idle_add.call_args_list
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0], call(self.mock_panel.append_log, "hello"))

    def test_mixed_cr_and_newline(self):
        remainder = self._flush(b"prog 30%\rinstalling foo\n")
        self.assertEqual(remainder, b"")
        calls = self.mock_glib.idle_add.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0], call(self.mock_panel.parse_progress, "prog 30%"))
        self.assertEqual(calls[1], call(self.mock_panel.append_log, "installing foo"))


if __name__ == "__main__":
    unittest.main()
