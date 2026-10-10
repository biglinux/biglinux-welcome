"""Tests for BigLinux Welcome — installation backend (install_backend.py) and the
privileged helper (scripts/package-install.sh).

The end-to-end tests run the real helper script unprivileged in its test mode
against a fake pacman, so no package is ever installed or removed.
"""

import io
import json
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

APP_DIR = (
    Path(__file__).resolve().parent.parent / "usr" / "share" / "biglinux" / "welcome"
)
sys.path.insert(0, str(APP_DIR))

import install_backend
from gi.repository import GLib
from install_backend import (
    Failure,
    InstallManager,
    JobState,
    PackageInstallJob,
    PlasmoidInstallJob,
    PlasmoidSource,
    ProgressParser,
    classify_failure,
    is_allowed_package,
    is_valid_package_name,
    parse_pacman_si,
    parse_preview,
    split_output_lines,
    tree_sha256,
    validate_plasmoid_dir,
)

HELPER = APP_DIR / "scripts" / "package-install.sh"

# Fake executables must not live on a noexec /tmp
_RUNTIME_DIR = os.environ.get("XDG_RUNTIME_DIR")
TMP_BASE = _RUNTIME_DIR if _RUNTIME_DIR and os.access(_RUNTIME_DIR, os.W_OK) else None


def run_job(job, timeout=20, on_start=None):
    """Start job through the manager and spin a main loop until it ends."""
    loop = GLib.MainLoop()
    job.connect("finished", lambda _j: loop.quit())
    GLib.timeout_add_seconds(timeout, loop.quit)
    assert InstallManager.get_default().start(job)
    if on_start:
        GLib.idle_add(lambda: on_start() and False)
    loop.run()
    return job


def write_script(path: Path, body: str) -> Path:
    path.write_text("#!/bin/bash\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class TestAllowlist(unittest.TestCase):
    def helper_list(self, name):
        script = HELPER.read_text()
        return set(
            re.search(rf"{name}=\(\n(.*?)\n\)", script, re.DOTALL).group(1).split()
        )

    def test_helper_allowlist_matches_python(self):
        self.assertEqual(
            self.helper_list("ALLOWED_PACKAGES"), set(install_backend.ALLOWED_PACKAGES)
        )

    def test_helper_repositories_match_python(self):
        self.assertEqual(
            self.helper_list("ALLOWED_REPOSITORIES"),
            set(install_backend.ALLOWED_REPOSITORIES),
        )

    def test_install_target(self):
        self.assertEqual(install_backend.install_target("bigcam"), "bigcam")
        self.assertEqual(
            install_backend.install_target("bigcam", "biglinux-stable"),
            "biglinux-stable/bigcam",
        )
        self.assertEqual(
            install_backend.install_target("bigcam", "biglinux-testing"), ""
        )
        self.assertEqual(install_backend.install_target("bigcam", "../etc"), "")
        self.assertEqual(install_backend.install_target("linux", "biglinux-stable"), "")

    def test_valid_names(self):
        for name in [
            "bigcam",
            "tts-biglinux",
            "zen-browser-bin",
            "lib32-foo",
            "gtk4",
            "c++utils",
            "python3.12",
        ]:
            self.assertTrue(is_valid_package_name(name), name)

    def test_rejects_injection_and_options(self):
        for name in [
            "",
            "-Syu",
            "--overwrite=*",
            "foo bar",
            "foo;rm -rf /",
            "$(id)",
            "a/b",
            "Foo",
            "x" * 200,
            None,
        ]:
            self.assertFalse(is_valid_package_name(name), repr(name))

    def test_allowed_requires_allowlist(self):
        self.assertTrue(is_allowed_package("bigcam"))
        self.assertFalse(is_allowed_package("linux"))
        self.assertFalse(is_allowed_package("google-chrome"))


class TestHelperValidation(unittest.TestCase):
    """The helper must refuse bad input before doing anything."""

    def run_helper(self, *args, env=None):
        return subprocess.run(
            [str(HELPER), *args],
            capture_output=True,
            text=True,
            env={"PATH": os.environ["PATH"], **(env or {})},
            timeout=30,
            check=False,
        )

    def test_rejects_not_allowed_package(self):
        r = self.run_helper("install", "linux")
        self.assertEqual(r.returncode, install_backend.HELPER_EXIT_USAGE)
        self.assertNotIn("STATUS:started", r.stdout)

    def test_rejects_injection(self):
        r = self.run_helper("install", "bigcam; touch /tmp/pwned")
        self.assertEqual(r.returncode, install_backend.HELPER_EXIT_USAGE)

    def test_rejects_unknown_mode(self):
        r = self.run_helper("remove", "bigcam")
        self.assertEqual(r.returncode, install_backend.HELPER_EXIT_USAGE)

    def test_rejects_extra_arguments(self):
        r = self.run_helper("install", "bigcam", "--overwrite=*")
        self.assertEqual(r.returncode, install_backend.HELPER_EXIT_USAGE)
        r = self.run_helper("install", "bigcam", "biglinux-stable", "extra")
        self.assertEqual(r.returncode, install_backend.HELPER_EXIT_USAGE)

    def test_rejects_not_allowed_repository(self):
        for repo in ("biglinux-testing", "core/../x", "-Syu", ""):
            if not repo:
                continue
            r = self.run_helper("install", "bigcam", repo)
            self.assertEqual(r.returncode, install_backend.HELPER_EXIT_USAGE, repo)
            self.assertNotIn("STATUS:started", r.stdout)

    @unittest.skipIf(os.geteuid() == 0, "needs an unprivileged user")
    def test_requires_root_outside_test_mode(self):
        r = self.run_helper("install", "bigcam")
        self.assertEqual(r.returncode, install_backend.HELPER_EXIT_NOT_ROOT)

    def test_never_uses_partial_upgrade(self):
        script = HELPER.read_text()
        self.assertNotRegex(script, r"-Sy\b(?!u)")
        self.assertIn("-Syu --needed", script)
        self.assertNotIn("yay", script)
        self.assertNotIn("curl", script)


class TestParsers(unittest.TestCase):
    SI_OUTPUT = textwrap.dedent("""\
        Repository      : biglinux-stable
        Name            : bigcam
        Version         : 26.03.30-2025
        Description     : Universal webcam control center
        Download Size   : 485.53 KiB

        Repository      : community-testing
        Name            : bigcam
        Version         : 26.09.07-0425
        Download Size   : 728.89 KiB

        Repository      : extra
        Name            : firefox
        Version         : 157.0.1-1
        Download Size   : 80.00 MiB
        """)

    def test_parse_si_first_repository_wins(self):
        pkgs = parse_pacman_si(self.SI_OUTPUT)
        self.assertEqual(pkgs["bigcam"].repository, "biglinux-stable")
        self.assertEqual(pkgs["community-testing/bigcam"].version, "26.09.07-0425")
        self.assertEqual(pkgs["biglinux-stable/bigcam"].version, "26.03.30-2025")
        self.assertEqual(pkgs["bigcam"].version, "26.03.30-2025")
        self.assertEqual(pkgs["firefox"].download_bytes, 80 * 1024**2)
        self.assertEqual(pkgs["bigcam"].download_bytes, int(485.53 * 1024))

    def test_parse_size(self):
        self.assertEqual(
            install_backend.parse_size("170.75 MiB"), int(170.75 * 1024**2)
        )
        self.assertEqual(install_backend.parse_size("1.5 GiB"), int(1.5 * 1024**3))
        self.assertEqual(install_backend.parse_size("512 B"), 512)
        self.assertEqual(install_backend.parse_size("garbage"), 0)
        self.assertEqual(install_backend.parse_size(""), 0)

    def test_parse_preview_success(self):
        out = "tk\t8.6.16-1\textra\t1000\nbiglinux-body-tracker\t24.11\tbiglinux-stable\t179044533\n"
        preview = parse_preview(0, out, "")
        self.assertEqual(len(preview.packages), 2)
        self.assertEqual(preview.download_bytes, 179045533)
        self.assertFalse(preview.nothing_to_do)

    def test_parse_preview_nothing_to_do(self):
        preview = parse_preview(0, "", "warning: bigcam is up to date -- skipping\n")
        self.assertTrue(preview.nothing_to_do)

    def test_parse_preview_error(self):
        preview = parse_preview(1, "", "error: target not found: foo\n")
        self.assertIn("target not found", preview.error)

    def test_preview_refuses_not_allowed(self):
        preview = install_backend.preview_install("linux")
        self.assertTrue(preview.error)


class TestSplitOutputLines(unittest.TestCase):
    """Line splitting of process output (previously window._flush_line_buffer)."""

    def test_newline(self):
        lines, rest = split_output_lines(b"hello world\n")
        self.assertEqual(lines, [("hello world", True)])
        self.assertEqual(rest, b"")

    def test_carriage_return_is_transient(self):
        lines, _rest = split_output_lines(b"progress 50%\r")
        self.assertEqual(lines, [("progress 50%", False)])

    def test_incomplete_line_kept(self):
        lines, rest = split_output_lines(b"partial")
        self.assertEqual(lines, [])
        self.assertEqual(rest, b"partial")

    def test_multiple_and_empty_lines(self):
        lines, rest = split_output_lines(b"\n\nline1\nline2\npartial")
        self.assertEqual(lines, [("line1", True), ("line2", True)])
        self.assertEqual(rest, b"partial")

    def test_mixed(self):
        lines, _ = split_output_lines(b"prog 30%\rinstalling foo\n")
        self.assertEqual(lines, [("prog 30%", False), ("installing foo", True)])

    def test_invalid_utf8_replaced(self):
        lines, _ = split_output_lines(b"caf\xe9\n")
        self.assertEqual(lines[0][0], "caf�")


class TestProgressParser(unittest.TestCase):
    def test_milestones_sorted_and_bounded(self):
        fractions = [f for _, f in ProgressParser.MILESTONES]
        self.assertEqual(fractions, sorted(fractions))
        self.assertTrue(all(0 < f <= 1 for f in fractions))

    def test_every_milestone_has_a_label(self):
        for keyword, _ in ProgressParser.MILESTONES:
            self.assertTrue(ProgressParser.PHASE_LABELS.get(keyword))

    def test_cancel_cutoff_is_a_milestone(self):
        self.assertIn(
            ProgressParser.CANCEL_CUTOFF, {f for _, f in ProgressParser.MILESTONES}
        )

    def test_real_pacman_sequence(self):
        parser = ProgressParser()
        sequence = [
            "resolving dependencies...",
            "looking for conflicting packages...",
            ":: Retrieving packages...",
            " bigcam-26.03.30-2025-any downloading...",
            "checking keyring...",
            "checking package integrity...",
            "loading package files...",
            "checking for file conflicts...",
            "checking available disk space...",
            ":: Processing package changes...",
            "installing bigcam...",
            ":: Running post-transaction hooks...",
        ]
        last = 0.0
        cancellable_seen = []
        for line in sequence:
            parser.feed(line)
            self.assertGreaterEqual(parser.fraction, last, line)
            last = parser.fraction
            cancellable_seen.append(parser.cancellable)
        self.assertEqual(parser.fraction, 0.95)
        self.assertTrue(cancellable_seen[0])
        self.assertFalse(cancellable_seen[-1])

    def test_download_line_updates_phase(self):
        parser = ProgressParser()
        parser.feed(":: Retrieving packages...")
        self.assertTrue(parser.feed(" firefox-157.0.1-1-x86_64 downloading..."))
        self.assertIn("firefox-157.0.1-1-x86_64", parser.phase)

    def test_progress_never_goes_backwards(self):
        parser = ProgressParser()
        parser.feed("checking keyring...")
        parser.feed("resolving dependencies...")
        self.assertEqual(parser.fraction, 0.55)


class TestClassifyFailure(unittest.TestCase):
    def check(self, lines, expected, rc=1, started=True):
        self.assertEqual(classify_failure(rc, lines, started), expected)

    def test_auth_denied(self):
        self.check([], Failure.AUTH_DENIED, rc=127, started=False)

    def test_locked_exit_code(self):
        self.check([], Failure.LOCKED, rc=install_backend.HELPER_EXIT_LOCKED)

    def test_locked_message(self):
        self.check(
            ["error: failed to init transaction (unable to lock database)"],
            Failure.LOCKED,
        )

    def test_network(self):
        self.check(
            [
                "error: failed retrieving file 'x.pkg.tar.zst' from mirror : Could not resolve host: mirror"
            ],
            Failure.NETWORK,
        )

    def test_outdated_database(self):
        self.check(
            [
                "error: failed retrieving file 'x' from m : The requested URL returned error: 404"
            ],
            Failure.OUTDATED_DATABASE,
        )

    def test_disk_space(self):
        self.check(
            [
                "error: Partition / too full: 10 blocks needed, 1 blocks free",
                "error: not enough free disk space",
            ],
            Failure.DISK_SPACE,
        )

    def test_dependencies(self):
        self.check(
            ["error: failed to prepare transaction (could not satisfy dependencies)"],
            Failure.DEPENDENCIES,
        )

    def test_conflicts(self):
        self.check(
            ["error: failed to commit transaction (conflicting files)"],
            Failure.CONFLICTS,
        )

    def test_signature(self):
        self.check(
            ['error: bigcam: signature from "X" is unknown trust'], Failure.SIGNATURE
        )

    def test_not_found(self):
        self.check(["error: target not found: foo"], Failure.NOT_FOUND)

    def test_unknown(self):
        self.check(["something odd"], Failure.UNKNOWN)

    def test_every_failure_has_a_message(self):
        for failure in Failure:
            if failure is not Failure.NONE:
                self.assertTrue(install_backend.failure_message(failure), failure)


class FakePacmanMixin:
    """Run PackageInstallJob → real helper (test mode) → fake pacman."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="welcome-test-", dir=TMP_BASE))
        self.lock = self.tmp / "db.lck"
        self.pacman = self.tmp / "pacman"
        self.marker = self.tmp / "sigint"
        self.patches = [
            patch.object(PackageInstallJob, "launcher", []),
            patch.object(PackageInstallJob, "stall_seconds", 0.2),
            patch.object(
                PackageInstallJob,
                "extra_env",
                {
                    "BIGLINUX_WELCOME_TEST": "1",
                    "BIGLINUX_WELCOME_TEST_PACMAN": str(self.pacman),
                    "BIGLINUX_WELCOME_TEST_LOCK": str(self.lock),
                },
            ),
            patch.object(
                install_backend, "PACMAN_LOCK", str(self.tmp / "app-side.lck")
            ),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()
        InstallManager._default = None
        __import__("shutil").rmtree(self.tmp, ignore_errors=True)

    def fake_pacman(self, body):
        write_script(self.pacman, body)

    def job(self, package="bigcam", verified=True):
        job = PackageInstallJob(package, "BigCam")
        job.verify_installed = lambda: verified
        return job


class TestPackageInstallJob(FakePacmanMixin, unittest.TestCase):
    PACMAN_OK = """\
        echo "args: $*"
        echo "resolving dependencies..."
        echo ":: Retrieving packages..."
        echo " bigcam-1-1-any downloading..."
        echo "checking keyring..."
        echo ":: Processing package changes..."
        echo "installing bigcam..."
        echo ":: Running post-transaction hooks..."
        exit 0
        """

    def test_success(self):
        self.fake_pacman(self.PACMAN_OK)
        job = run_job(self.job())
        self.assertIs(job.state, JobState.SUCCEEDED, job.log_lines)
        self.assertEqual(job.fraction, 1.0)
        self.assertIn("args: -S --needed --noconfirm -- bigcam", job.log_lines)
        self.assertIn("installing bigcam...", job.log_lines)

    def test_upgrade_mode_uses_full_upgrade(self):
        self.fake_pacman(self.PACMAN_OK)
        job = PackageInstallJob("bigcam", "BigCam", upgrade=True)
        job.verify_installed = lambda: True
        run_job(job)
        self.assertIn("args: -Syu --needed --noconfirm -- bigcam", job.log_lines)

    def test_pinned_repository_reaches_pacman(self):
        self.fake_pacman(self.PACMAN_OK)
        job = PackageInstallJob("bigcam", "BigCam", repository="biglinux-stable")
        job.verify_installed = lambda: True
        run_job(job)
        self.assertIs(job.state, JobState.SUCCEEDED, job.log_lines)
        self.assertIn(
            "args: -S --needed --noconfirm -- biglinux-stable/bigcam", job.log_lines
        )

    def test_not_allowed_repository_never_runs(self):
        self.fake_pacman(self.PACMAN_OK)
        job = PackageInstallJob("bigcam", "BigCam", repository="biglinux-testing")
        job.verify_installed = lambda: True
        run_job(job)
        self.assertIs(job.failure, Failure.NOT_ALLOWED)
        self.assertEqual(job.log_lines, [])

    def test_success_requires_verification(self):
        self.fake_pacman(self.PACMAN_OK)
        job = run_job(self.job(verified=False))
        self.assertIs(job.state, JobState.FAILED)
        self.assertIs(job.failure, Failure.VERIFICATION)

    def test_network_failure(self):
        self.fake_pacman("""\
            echo ":: Retrieving packages..."
            echo "error: failed retrieving file 'bigcam.pkg.tar.zst' from mirror : Could not resolve host: mirror" >&2
            echo "error: failed to commit transaction (failed to retrieve some files)" >&2
            exit 1
            """)
        job = run_job(self.job())
        self.assertIs(job.state, JobState.FAILED)
        self.assertIs(job.failure, Failure.NETWORK)

    def test_package_manager_busy(self):
        self.fake_pacman(self.PACMAN_OK)
        self.lock.touch()
        job = run_job(self.job())
        self.assertIs(job.state, JobState.FAILED)
        self.assertIs(job.failure, Failure.LOCKED)

    def test_busy_detected_before_authentication(self):
        (self.tmp / "app-side.lck").touch()
        self.fake_pacman(self.PACMAN_OK)
        job = run_job(self.job())
        self.assertIs(job.failure, Failure.LOCKED)
        self.assertFalse(any("args:" in line for line in job.log_lines))

    def test_cancel_sends_sigint_to_pacman(self):
        self.fake_pacman(f"""\
            trap 'echo "interrupted"; touch {self.marker}; exit 130' INT
            echo ":: Retrieving packages..."
            for i in $(seq 1 100); do sleep 0.1; done
            exit 0
            """)
        job = self.job()

        def cancel_when_downloading():
            if job.phase:
                self.assertTrue(job.cancel())
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        run_job(job, on_start=lambda: GLib.timeout_add(100, cancel_when_downloading))
        self.assertIs(job.state, JobState.CANCELLED, job.log_lines)
        self.assertTrue(self.marker.exists(), "pacman did not receive SIGINT")

    def test_cannot_cancel_after_changes_started(self):
        self.fake_pacman("""\
            echo ":: Processing package changes..."
            sleep 1
            exit 0
            """)
        job = self.job()
        refused = []

        def try_cancel():
            if not job.cancellable:
                refused.append(job.cancel())
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        run_job(job, on_start=lambda: GLib.timeout_add(50, try_cancel))
        self.assertEqual(refused, [False])
        self.assertIs(job.state, JobState.SUCCEEDED)

    def test_not_allowed_package_never_runs(self):
        self.fake_pacman(self.PACMAN_OK)
        job = run_job(self.job(package="linux"))
        self.assertIs(job.failure, Failure.NOT_ALLOWED)
        self.assertEqual(job.log_lines, [])


class TestAuthentication(FakePacmanMixin, unittest.TestCase):
    """pkexec exit codes: 126 = dialog dismissed, 127 = not authorized."""

    def with_pkexec(self, exit_code):
        fake_pkexec = write_script(self.tmp / "pkexec", f"exit {exit_code}\n")
        PackageInstallJob.launcher = [str(fake_pkexec)]

    def test_dismissed(self):
        self.with_pkexec(126)
        job = run_job(self.job())
        self.assertIs(job.state, JobState.AUTH_CANCELLED)
        self.assertIs(job.failure, Failure.NONE)

    def test_not_authorized(self):
        self.with_pkexec(127)
        job = run_job(self.job())
        self.assertIs(job.state, JobState.FAILED)
        self.assertIs(job.failure, Failure.AUTH_DENIED)


class TestInstallManager(FakePacmanMixin, unittest.TestCase):
    def test_one_transaction_at_a_time(self):
        self.fake_pacman("sleep 0.5; exit 0\n")
        manager = InstallManager.get_default()
        first, second = self.job(), self.job()
        loop = GLib.MainLoop()
        first.connect("finished", lambda _j: loop.quit())
        self.assertTrue(manager.start(first))
        self.assertTrue(manager.busy)
        self.assertFalse(manager.start(second))
        GLib.timeout_add_seconds(10, loop.quit)
        loop.run()
        self.assertFalse(manager.busy)
        self.assertIs(second.state, JobState.PENDING)


def make_plasmoid_archive(
    directory: Path, plugin_id="ChatAI-Plasmoid", api="6.0", extra=None
):
    root = directory / "src" / f"{plugin_id}-abc"
    (root / "contents" / "ui").mkdir(parents=True)
    (root / "metadata.json").write_text(
        json.dumps(
            {
                "KPackageStructure": "Plasma/Applet",
                "KPlugin": {"Id": plugin_id, "Name": "ChatAI"},
                "X-Plasma-API-Minimum-Version": api,
            }
        )
    )
    (root / "contents" / "ui" / "main.qml").write_text("import QtQuick\nItem {}\n")
    for name, content in (extra or {}).items():
        (root / name).write_text(content)
    archive = directory / "plasmoid.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(root, arcname=root.name)
    return archive, tree_sha256(str(root))


class TestPlasmoid(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="welcome-plasmoid-", dir=TMP_BASE))

    def tearDown(self):
        InstallManager._default = None
        __import__("shutil").rmtree(self.tmp, ignore_errors=True)

    def test_tree_hash_ignores_archive_metadata(self):
        a = self.tmp / "a"
        b = self.tmp / "b"
        for d in (a, b):
            (d / "x").mkdir(parents=True)
            (d / "x" / "f.txt").write_text("same")
        os.utime(b / "x" / "f.txt", (0, 0))
        self.assertEqual(tree_sha256(str(a)), tree_sha256(str(b)))
        (b / "x" / "f.txt").write_text("changed")
        self.assertNotEqual(tree_sha256(str(a)), tree_sha256(str(b)))

    def test_validate_metadata(self):
        _archive, _ = make_plasmoid_archive(self.tmp)
        root = next((self.tmp / "src").iterdir())
        self.assertEqual(validate_plasmoid_dir(str(root), "ChatAI-Plasmoid"), "")
        self.assertTrue(validate_plasmoid_dir(str(root), "Other"))

    def test_rejects_plasma5_widget(self):
        make_plasmoid_archive(self.tmp, api="5.0")
        root = next((self.tmp / "src").iterdir())
        self.assertIn("Plasma 6", validate_plasmoid_dir(str(root), "ChatAI-Plasmoid"))

    def test_pinned_source_is_https_and_pinned_to_a_commit(self):
        source = install_backend.CHATAI_SOURCE
        self.assertTrue(
            source.url.startswith(
                "https://github.com/biglinux/ChatAI-Plasmoid/archive/"
            )
        )
        self.assertRegex(source.url, r"/[0-9a-f]{40}\.tar\.gz$")
        self.assertRegex(source.tree_sha256, r"^[0-9a-f]{64}$")

    def run_plasmoid_job(self, archive, digest):
        source = PlasmoidSource("ChatAI-Plasmoid", archive.as_uri(), digest)
        job = PlasmoidInstallJob(source, "ChatAI")
        job.package_root = str(self.tmp / "root")
        return run_job(job, timeout=60)

    @unittest.skipUnless(
        __import__("shutil").which("kpackagetool6"), "kpackagetool6 not installed"
    )
    def test_install_into_private_root(self):
        archive, digest = make_plasmoid_archive(self.tmp)
        job = self.run_plasmoid_job(archive, digest)
        self.assertIs(job.state, JobState.SUCCEEDED, job.log_lines)
        self.assertTrue(
            (self.tmp / "root" / "ChatAI-Plasmoid" / "metadata.json").exists()
        )

    @unittest.skipUnless(
        __import__("shutil").which("kpackagetool6"), "kpackagetool6 not installed"
    )
    def test_tampered_archive_is_not_installed(self):
        archive, _digest = make_plasmoid_archive(
            self.tmp, extra={"evil.sh": "rm -rf ~"}
        )
        job = self.run_plasmoid_job(archive, "0" * 64)
        self.assertIs(job.state, JobState.FAILED)
        self.assertIs(job.failure, Failure.INTEGRITY)
        self.assertFalse((self.tmp / "root").exists())

    def test_path_traversal_archive_rejected(self):
        archive = self.tmp / "evil.tar.gz"
        with tarfile.open(archive, "w:gz") as tar:
            data = b"owned"
            info = tarfile.TarInfo("../../escape.txt")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        _dir, error = PlasmoidInstallJob._extract(str(archive), str(self.tmp / "out"))
        self.assertTrue(error)
        self.assertFalse((self.tmp.parent / "escape.txt").exists())

    @unittest.skipUnless(os.environ.get("RUN_NETWORK_TESTS"), "set RUN_NETWORK_TESTS=1")
    @unittest.skipUnless(
        __import__("shutil").which("kpackagetool6"), "kpackagetool6 not installed"
    )
    def test_real_chatai_download_matches_pinned_hash(self):
        job = PlasmoidInstallJob(install_backend.CHATAI_SOURCE, "ChatAI")
        job.package_root = str(self.tmp / "root")
        run_job(job, timeout=120)
        self.assertIs(job.state, JobState.SUCCEEDED, job.log_lines)


if __name__ == "__main__":
    unittest.main()
