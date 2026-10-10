"""BigLinux Welcome — Application installation backend.

Everything that touches the package manager lives here, so the browser page,
the "Applications to Install" page and the launcher cards share one secure
implementation:

* package queries (installed / available / transaction preview) run as the
  normal user and never modify the system;
* installations run through ``pkexec`` and the allowlisted helper script
  ``scripts/package-install.sh`` — one pacman transaction at a time;
* the ChatAI Plasma widget, which has no package, is downloaded from a pinned
  commit, verified by content hash and installed per user with kpackagetool6.

Jobs run in worker threads and report back on the GTK main loop through
GObject signals, so the interface never blocks.
"""

from __future__ import annotations

import enum
import gettext
import hashlib
import json
import os
import re
import select
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from typing import ClassVar

import gi

gi.require_version("Gio", "2.0")

from gi.repository import Gio, GLib, GObject
from utils import APP_PATH

_ = gettext.gettext


def N_(message: str) -> str:
    """Mark a string for extraction without translating it yet."""
    return message


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HELPER_PATH = os.path.join(APP_PATH, "scripts", "package-install.sh")
PACMAN_LOCK = "/var/lib/pacman/db.lck"
PACMAN_SYNC_DIR = "/var/lib/pacman/sync"

# Packages the welcome app may install. The privileged helper keeps its own
# copy of this list (tests/test_install_backend.py checks that both match).
ALLOWED_PACKAGES = frozenset(
    {
        # Hardware and features
        "biglinux-driver-manager",
        "biglinux-noise-reduction-pipewire",
        "tts-biglinux",
        # Applications to Install
        "big-advogados",
        "bigame-mode",
        "big-remote-play",
        "bigcam",
        "biglinux-body-tracker",
        # Browsers available in the configured repositories
        "brave-browser",
        "chromium",
        "falkon",
        "firefox",
        "librewolf",
        "vivaldi",
        "zen-browser-bin",
    }
)

# Repositories an application may be pinned to (pages.yaml "repository"),
# e.g. to install from biglinux-stable even when biglinux-testing is enabled
# and listed first in pacman.conf. Also kept in sync with the helper.
ALLOWED_REPOSITORIES = frozenset({"biglinux-stable"})

_PACKAGE_NAME_RE = re.compile(r"^[a-z0-9@_+][a-z0-9@._+-]{0,127}$")

# Exit codes of scripts/package-install.sh (keep in sync with the script)
HELPER_EXIT_USAGE = 2
HELPER_EXIT_LOCKED = 3
HELPER_EXIT_NOT_ROOT = 4
# Exit codes of pkexec itself
PKEXEC_EXIT_DISMISSED = 126
PKEXEC_EXIT_NOT_AUTHORIZED = 127

HELPER_STARTED_MARKER = "STATUS:started"

# Sync databases older than this make "outdated mirror" failures likely
STALE_DATABASE_DAYS = 14


def _c_locale_env() -> dict[str, str]:
    """Environment forcing untranslated output, so it can be parsed."""
    env = dict(os.environ)
    env.update({"LC_ALL": "C", "LANG": "C", "LANGUAGE": "C"})
    return env


# ---------------------------------------------------------------------------
# Package queries (read-only, run as the user)
# ---------------------------------------------------------------------------


def is_valid_package_name(name: str) -> bool:
    """Check that name is a syntactically valid pacman package name."""
    return isinstance(name, str) and bool(_PACKAGE_NAME_RE.match(name))


def is_allowed_package(name: str) -> bool:
    """Check that name is valid and in the installation allowlist."""
    return is_valid_package_name(name) and name in ALLOWED_PACKAGES


def install_target(package: str, repository: str = "") -> str:
    """pacman target for package, pinned to repository when given.

    Returns "" when the package or the repository is not allowed."""
    if not is_allowed_package(package):
        return ""
    if not repository:
        return package
    if repository not in ALLOWED_REPOSITORIES:
        return ""
    return f"{repository}/{package}"


def _is_valid_target(target: str) -> bool:
    repository, _sep, name = target.rpartition("/")
    return is_valid_package_name(name) and (
        not repository or is_valid_package_name(repository)
    )


def _run_pacman(args: list[str], timeout: float = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["pacman", *args],
        capture_output=True,
        text=True,
        env=_c_locale_env(),
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )


def installed_packages(names: list[str] | set[str]) -> set[str]:
    """Return the subset of names installed on the system."""
    names = sorted(n for n in names if is_valid_package_name(n))
    if not names:
        return set()
    try:
        result = _run_pacman(["-Q", "--", *names])
    except (OSError, subprocess.TimeoutExpired):
        return set()
    found = set()
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts and parts[0] in names:
            found.add(parts[0])
    return found


def is_package_installed(name: str) -> bool:
    return name in installed_packages([name])


@dataclass(frozen=True)
class RepoPackage:
    """A package available in a configured repository."""

    name: str
    version: str
    repository: str
    download_bytes: int = 0


def parse_pacman_si(output: str) -> dict[str, RepoPackage]:
    """Parse ``pacman -Si`` output, keyed by "name" and by "repository/name".

    For the plain name the first repository listed wins, matching the
    order pacman itself uses when installing."""
    packages: dict[str, RepoPackage] = {}
    for block in re.split(r"\n\s*\n", output):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            key, sep, value = line.partition(":")
            if sep and not line.startswith(" "):
                fields[key.strip()] = value.strip()
        name = fields.get("Name")
        if not name:
            continue
        package = RepoPackage(
            name=name,
            version=fields.get("Version", ""),
            repository=fields.get("Repository", ""),
            download_bytes=parse_size(fields.get("Download Size", "")),
        )
        packages.setdefault(name, package)
        packages.setdefault(f"{package.repository}/{name}", package)
    return packages


def repo_packages(names: list[str] | set[str]) -> dict[str, RepoPackage]:
    """Look up package names or "repository/name" targets in the local copy
    of the sync databases (works offline)."""
    names = sorted(n for n in names if _is_valid_target(n))
    if not names:
        return {}
    try:
        result = _run_pacman(["-Si", "--", *names])
    except (OSError, subprocess.TimeoutExpired):
        return {}
    return parse_pacman_si(result.stdout)


@dataclass
class TransactionPreview:
    """What ``pacman -S --needed <package>`` would do."""

    packages: list[tuple[str, str, str, int]] = field(default_factory=list)
    error: str = ""

    @property
    def download_bytes(self) -> int:
        return sum(p[3] for p in self.packages)

    @property
    def nothing_to_do(self) -> bool:
        return not self.error and not self.packages


def parse_preview(returncode: int, stdout: str, stderr: str) -> TransactionPreview:
    preview = TransactionPreview()
    if returncode != 0:
        errors = [
            ln.removeprefix("error:").strip()
            for ln in (stderr + "\n" + stdout).splitlines()
            if ln.startswith(("error:", ":: "))
        ]
        preview.error = "\n".join(errors) or stderr.strip() or stdout.strip()
        return preview
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 4:
            continue
        name, version, repo, size = parts
        try:
            size_bytes = int(size)
        except ValueError:
            size_bytes = 0
        preview.packages.append((name, version, repo, size_bytes))
    return preview


def preview_install(package: str, repository: str = "") -> TransactionPreview:
    """List the packages (with dependencies) an installation would download.

    Uses ``pacman -Sp``, which only reads the sync databases."""
    target = install_target(package, repository)
    if not target:
        return TransactionPreview(error=_("This package is not allowed."))
    try:
        result = _run_pacman(
            [
                "-Sp",
                "--needed",
                "--print-format",
                "%n\t%v\t%r\t%s",
                "--",
                target,
            ]
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        return TransactionPreview(error=str(e))
    return parse_preview(result.returncode, result.stdout, result.stderr)


def is_pacman_locked() -> bool:
    return os.path.exists(PACMAN_LOCK)


def sync_database_age_days() -> float | None:
    """Days since the package databases were last refreshed."""
    try:
        mtimes = [
            entry.stat().st_mtime
            for entry in os.scandir(PACMAN_SYNC_DIR)
            if entry.name.endswith(".db")
        ]
    except OSError:
        return None
    if not mtimes:
        return None
    return max(0.0, (time.time() - max(mtimes)) / 86400)


_SIZE_UNITS = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3, "TiB": 1024**4}


def parse_size(text: str) -> int:
    """Parse a pacman size such as "170.75 MiB" into bytes (0 if unknown)."""
    match = re.match(r"^\s*([\d.,]+)\s*([KMGT]?i?B)\s*$", text or "")
    if not match or match.group(2) not in _SIZE_UNITS:
        return 0
    try:
        value = float(match.group(1).replace(",", "."))
    except ValueError:
        return 0
    return int(value * _SIZE_UNITS[match.group(2)])


def format_size(num_bytes: int) -> str:
    """Localized size in binary units, as pacman reports them."""
    return GLib.format_size_full(num_bytes, GLib.FormatSizeFlags.IEC_UNITS)


def is_network_available() -> bool:
    try:
        return Gio.NetworkMonitor.get_default().get_network_available()
    except GLib.Error:
        return True


# ---------------------------------------------------------------------------
# Output handling
# ---------------------------------------------------------------------------


def split_output_lines(buf: bytes) -> tuple[list[tuple[str, bool]], bytes]:
    """Split buffered process output into complete lines.

    Returns ``([(line, is_newline_terminated), ...], remainder)``. Lines ending
    in a carriage return are transient progress updates. Empty lines are
    dropped."""
    lines: list[tuple[str, bool]] = []
    while True:
        idx_n = buf.find(b"\n")
        idx_r = buf.find(b"\r")
        if idx_n < 0 and idx_r < 0:
            break
        is_newline = idx_n >= 0 and (idx_r < 0 or idx_n <= idx_r)
        idx = idx_n if is_newline else idx_r
        line = buf[:idx].decode("utf-8", errors="replace")
        buf = buf[idx + 1 :]
        if line:
            lines.append((line, is_newline))
    return lines, buf


class ProgressParser:
    """Turn pacman output into a progress fraction and a readable phase.

    Pacman prints no progress bars when its output is piped, so progress is
    estimated from the milestones every transaction goes through."""

    # Keywords must match pacman's untranslated (LC_ALL=C) output
    MILESTONES: ClassVar[list[tuple[str, float]]] = [
        ("synchronizing", 0.05),
        ("resolving dependencies", 0.10),
        ("looking for conflicting", 0.15),
        ("retrieving", 0.20),
        ("checking key", 0.55),
        ("checking package integrity", 0.60),
        ("loading package", 0.65),
        ("checking for file conflicts", 0.70),
        ("checking available disk space", 0.75),
        ("processing package changes", 0.80),
        ("installing", 0.85),
        ("upgrading", 0.85),
        ("running post-transaction hooks", 0.95),
    ]

    PHASE_LABELS: ClassVar[dict[str, str]] = {
        "synchronizing": N_("Synchronizing databases…"),
        "resolving dependencies": N_("Resolving dependencies…"),
        "looking for conflicting": N_("Checking for conflicts…"),
        "retrieving": N_("Downloading packages…"),
        "checking key": N_("Verifying signatures…"),
        "checking package integrity": N_("Verifying integrity…"),
        "loading package": N_("Loading packages…"),
        "checking for file conflicts": N_("Checking for conflicts…"),
        "checking available disk space": N_("Checking disk space…"),
        "processing package changes": N_("Applying changes…"),
        "installing": N_("Installing…"),
        "upgrading": N_("Upgrading…"),
        "running post-transaction hooks": N_("Running post-install hooks…"),
    }

    # Cancelling is refused once pacman starts changing the filesystem
    CANCEL_CUTOFF = 0.80  # "processing package changes"

    # " firefox-138.0.4-1  45.2 MiB  12.5 MiB/s 00:03 [###] 58%"
    _RE_DOWNLOAD = re.compile(r"(\d+(?:\.\d+)?\s*[KMG]iB/s).*?(\d{1,3})%")

    def __init__(self) -> None:
        self.fraction = 0.0
        self.phase = ""

    @property
    def cancellable(self) -> bool:
        return self.fraction < self.CANCEL_CUTOFF

    def feed(self, line: str) -> bool:
        """Parse one line. Returns True if fraction or phase changed."""
        lower = line.lower()
        for keyword, fraction in self.MILESTONES:
            if keyword in lower and fraction > self.fraction:
                self.fraction = fraction
                self.phase = _(self.PHASE_LABELS[keyword])
                return True

        if not 0.05 <= self.fraction < 0.55:
            return False
        if "downloading" in lower:
            name = line.strip().replace("downloading...", "").strip()
            if name:
                self.phase = _("Downloading {name}…").format(name=name)
                return True
            return False
        match = self._RE_DOWNLOAD.search(line)
        if match:
            pct = min(100, int(match.group(2)))
            self.fraction = max(self.fraction, 0.20 + (pct / 100.0) * 0.35)
            self.phase = _("Downloading… {pct}% ({speed})").format(
                pct=pct, speed=match.group(1)
            )
            return True
        return False


# ---------------------------------------------------------------------------
# Failures
# ---------------------------------------------------------------------------


class Failure(enum.Enum):
    NONE = "none"
    AUTH_DENIED = "auth-denied"
    LOCKED = "locked"
    OFFLINE = "offline"
    NETWORK = "network"
    OUTDATED_DATABASE = "outdated-database"
    DISK_SPACE = "disk-space"
    NOT_FOUND = "not-found"
    DEPENDENCIES = "dependencies"
    CONFLICTS = "conflicts"
    SIGNATURE = "signature"
    VERIFICATION = "verification"
    INTEGRITY = "integrity"
    NOT_ALLOWED = "not-allowed"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


FAILURE_MESSAGES = {
    Failure.AUTH_DENIED: N_(
        "Authentication failed. Administrator permission is required to install applications."
    ),
    Failure.LOCKED: N_(
        "Another program is using the package manager. Wait for it to finish and try again."
    ),
    Failure.OFFLINE: N_(
        "No internet connection. Connect to the internet and try again."
    ),
    Failure.NETWORK: N_(
        "Could not download the packages. Check your internet connection and try again."
    ),
    Failure.OUTDATED_DATABASE: N_(
        "The package lists are out of date, so the mirrors no longer have the requested files. Update the system and try again."
    ),
    Failure.DISK_SPACE: N_(
        "There is not enough free disk space to install this application."
    ),
    Failure.NOT_FOUND: N_("The package was not found in the configured repositories."),
    Failure.DEPENDENCIES: N_("Some dependencies could not be resolved."),
    Failure.CONFLICTS: N_("The package conflicts with software already installed."),
    Failure.SIGNATURE: N_(
        "A package signature could not be verified. The keyring may need to be updated."
    ),
    Failure.INTEGRITY: N_(
        "The downloaded files did not pass the integrity check. Nothing was installed."
    ),
    Failure.VERIFICATION: N_(
        "The installation finished, but the application could not be found on the system."
    ),
    Failure.NOT_ALLOWED: N_("This package is not allowed."),
    Failure.UNSUPPORTED: N_(
        "This application is not supported on the current desktop."
    ),
    Failure.UNKNOWN: N_(
        "The installation failed. See the details for more information."
    ),
}


def failure_message(failure: Failure) -> str:
    message = FAILURE_MESSAGES.get(failure)
    return _(message) if message else ""


# Ordered: the first matching pattern wins
_FAILURE_PATTERNS = [
    (Failure.LOCKED, ("unable to lock database", "database is locked")),
    (Failure.DISK_SPACE, ("not enough free disk space", "no space left on device")),
    (Failure.OUTDATED_DATABASE, ("the requested url returned error: 404", "error 404")),
    (
        Failure.NETWORK,
        (
            "could not resolve host",
            "failed retrieving file",
            "failed to retrieve some files",
            "connection timed out",
            "couldn't connect to server",
            "operation too slow",
            "network is unreachable",
            "download library error",
        ),
    ),
    (
        Failure.SIGNATURE,
        (
            "invalid or corrupted package (pgp signature)",
            "unknown trust",
            "signature from",
        ),
    ),
    (Failure.NOT_FOUND, ("target not found",)),
    (
        Failure.DEPENDENCIES,
        ("unable to satisfy dependency", "could not satisfy dependencies"),
    ),
    (Failure.CONFLICTS, ("conflicting files", "are in conflict", "conflicts with")),
]


def classify_failure(returncode: int, lines: list[str], started: bool) -> Failure:
    """Work out why a helper run failed from its exit code and output."""
    if not started and returncode == PKEXEC_EXIT_NOT_AUTHORIZED:
        return Failure.AUTH_DENIED
    if returncode == HELPER_EXIT_LOCKED:
        return Failure.LOCKED
    if returncode in (HELPER_EXIT_USAGE, HELPER_EXIT_NOT_ROOT):
        return Failure.NOT_ALLOWED
    text = "\n".join(lines).lower()
    for failure, patterns in _FAILURE_PATTERNS:
        if any(p in text for p in patterns):
            return failure
    return Failure.UNKNOWN


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


class JobState(enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    AUTH_CANCELLED = "auth-cancelled"


class InstallJob(GObject.Object):
    """Base class for an installation running in a worker thread.

    Signals are always emitted on the GTK main loop:
      log(line)                    — a new output line
      progress(fraction, phase)    — progress estimate changed
      cancellable-changed(bool)    — whether cancel() is still possible
      finished()                   — check ``state`` and ``failure``
    """

    __gsignals__: ClassVar[dict] = {
        "log": (GObject.SignalFlags.RUN_LAST, None, (str,)),
        "progress": (GObject.SignalFlags.RUN_LAST, None, (float, str)),
        "cancellable-changed": (GObject.SignalFlags.RUN_LAST, None, (bool,)),
        "finished": (GObject.SignalFlags.RUN_LAST, None, ()),
    }

    def __init__(self, label: str) -> None:
        super().__init__()
        self.label = label
        self.state = JobState.PENDING
        self.failure = Failure.NONE
        self.fraction = 0.0
        self.phase = ""
        self.cancellable = True
        self.log_lines: list[str] = []
        self._cancel_requested = threading.Event()

    # -- Public API (main thread) --

    def start(self) -> None:
        if self.state is not JobState.PENDING:
            return
        self.state = JobState.RUNNING
        threading.Thread(target=self._thread_main, daemon=True).start()

    @property
    def running(self) -> bool:
        return self.state is JobState.RUNNING

    @property
    def cancel_requested(self) -> bool:
        return self._cancel_requested.is_set()

    def cancel(self) -> bool:
        """Request cancellation. Returns False when it is too late."""
        if self.cancel_requested:
            return True
        if not self.running or not self.cancellable:
            return False
        self._cancel_requested.set()
        self._on_cancel()
        return True

    def failure_text(self) -> str:
        return failure_message(self.failure)

    # -- For subclasses (worker thread) --

    def _run(self) -> tuple[JobState, Failure]:
        raise NotImplementedError

    def _on_cancel(self) -> None:
        """Called on the main thread after cancel() was accepted."""

    def _log(self, line: str) -> None:
        GLib.idle_add(self._emit_log, line)

    def _progress(self, fraction: float, phase: str) -> None:
        GLib.idle_add(self._emit_progress, fraction, phase)

    def _set_cancellable(self, cancellable: bool) -> None:
        GLib.idle_add(self._emit_cancellable, cancellable)

    # -- Internal --

    def _thread_main(self) -> None:
        try:
            state, failure = self._run()
        except Exception as e:  # noqa: BLE001 — never leave a job hanging
            self._log(f"error: {e}")
            state, failure = JobState.FAILED, Failure.UNKNOWN
        GLib.idle_add(self._emit_finished, state, failure)

    def _emit_log(self, line: str) -> bool:
        self.log_lines.append(line)
        self.emit("log", line)
        return GLib.SOURCE_REMOVE

    def _emit_progress(self, fraction: float, phase: str) -> bool:
        self.fraction = fraction
        self.phase = phase
        self.emit("progress", fraction, phase)
        return GLib.SOURCE_REMOVE

    def _emit_cancellable(self, cancellable: bool) -> bool:
        if cancellable != self.cancellable:
            self.cancellable = cancellable
            self.emit("cancellable-changed", cancellable)
        return GLib.SOURCE_REMOVE

    def _emit_finished(self, state: JobState, failure: Failure) -> bool:
        self.state = state
        self.failure = failure if state is JobState.FAILED else Failure.NONE
        if state is JobState.SUCCEEDED:
            self.fraction = 1.0
        self.emit("finished")
        return GLib.SOURCE_REMOVE


class PackageInstallJob(InstallJob):
    """Install one allowlisted package with pacman through pkexec.

    ``repository`` pins the package to an allowlisted repository.
    ``upgrade=True`` performs a full system upgrade together with the
    installation (``pacman -Syu``) — offered only after the user confirms it,
    when the package databases are too old for a plain install."""

    # Overridable by tests
    launcher: ClassVar[list[str]] = ["pkexec"]
    helper_path: str = HELPER_PATH
    extra_env: ClassVar[dict[str, str]] = {}
    stall_seconds = 5.0
    timeout_seconds = 3600

    def __init__(
        self, package: str, label: str, upgrade: bool = False, repository: str = ""
    ) -> None:
        super().__init__(label)
        self.package = package
        self.repository = repository
        self.upgrade = upgrade
        self._proc: subprocess.Popen[bytes] | None = None
        self._parser = ProgressParser()

    def verify_installed(self) -> bool:
        return is_package_installed(self.package)

    def _on_cancel(self) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            return
        try:
            proc.stdin.write(b"cancel\n")
            proc.stdin.flush()
        except (BrokenPipeError, OSError, ValueError):
            pass
        self._log(_("Cancelling installation…"))

    def _run(self) -> tuple[JobState, Failure]:
        if not install_target(self.package, self.repository):
            return JobState.FAILED, Failure.NOT_ALLOWED
        if is_pacman_locked():
            return JobState.FAILED, Failure.LOCKED

        mode = "upgrade-install" if self.upgrade else "install"
        cmd = [*self.launcher, self.helper_path, mode, self.package]
        if self.repository:
            cmd.append(self.repository)
        env = _c_locale_env()
        env.update(self.extra_env)
        self._progress(0.0, _("Waiting for authentication…"))
        try:
            self._proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=env,
                bufsize=0,
            )
        except OSError as e:
            self._log(str(e))
            return JobState.FAILED, Failure.UNKNOWN

        lines, started = self._read_output(self._proc)
        try:
            returncode = self._proc.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self._log(_("The installer did not finish in time."))
            return JobState.FAILED, Failure.UNKNOWN
        finally:
            if self._proc.stdin:
                try:
                    self._proc.stdin.close()
                except OSError:
                    pass

        if not started and returncode == PKEXEC_EXIT_DISMISSED:
            return JobState.AUTH_CANCELLED, Failure.NONE
        if returncode == 0:
            if self.verify_installed():
                return JobState.SUCCEEDED, Failure.NONE
            return JobState.FAILED, Failure.VERIFICATION
        if self.cancel_requested:
            return JobState.CANCELLED, Failure.NONE
        return JobState.FAILED, classify_failure(returncode, lines, started)

    def _read_output(self, proc: subprocess.Popen[bytes]) -> tuple[list[str], bool]:
        """Read output until EOF, forwarding lines and progress."""
        assert proc.stdout is not None
        fd = proc.stdout.fileno()
        buf = b""
        lines: list[str] = []
        started = False
        stall_notified = False
        deadline = time.monotonic() + self.timeout_seconds

        while time.monotonic() < deadline:
            ready, _w, _x = select.select([fd], [], [], self.stall_seconds)
            if not ready:
                if started and not stall_notified:
                    stall_notified = True
                    self._log(_("Still working…"))
                continue
            stall_notified = False
            chunk = os.read(fd, 4096)
            if not chunk:
                if buf:
                    lines.append(buf.decode("utf-8", errors="replace"))
                    self._handle_line(lines[-1], True)
                break
            buf += chunk
            split, buf = split_output_lines(buf)
            for line, is_newline in split:
                if line.startswith("STATUS:"):
                    if line == HELPER_STARTED_MARKER:
                        started = True
                        self._progress(0.02, _("Preparing installation…"))
                    continue
                if is_newline:
                    lines.append(line)
                self._handle_line(line, is_newline)
        return lines, started

    def _handle_line(self, line: str, is_newline: bool) -> None:
        if is_newline:
            self._log(line)
        if self._parser.feed(line):
            self._progress(self._parser.fraction, self._parser.phase)
            self._set_cancellable(self._parser.cancellable)


# ---------------------------------------------------------------------------
# ChatAI Plasma widget
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlasmoidSource:
    """A Plasma widget pinned to an exact upstream commit."""

    plugin_id: str
    url: str
    tree_sha256: str
    max_bytes: int = 20 * 1024 * 1024


# biglinux/ChatAI-Plasmoid has no package in the configured repositories.
# Bump the commit and hash together after reviewing upstream changes; the
# hash covers every file path and content (see tree_sha256()).
CHATAI_SOURCE = PlasmoidSource(
    plugin_id="ChatAI-Plasmoid",
    url=(
        "https://github.com/biglinux/ChatAI-Plasmoid/archive/"
        "498426338a2d1f524027fdd604882545bf8edd58.tar.gz"
    ),
    tree_sha256="3144c6a15a4b35344280aa0ef8b2c4e38c1f617f23fe693ae75f2afa3b448320",
)

PLASMOID_SOURCES = {CHATAI_SOURCE.plugin_id: CHATAI_SOURCE}


def is_plasma_session() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "")
    return "KDE" in desktop or "Plasma" in desktop.split(":")


def plasmoid_dirs() -> list[str]:
    data_home = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    data_dirs = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    return [
        os.path.join(d, "plasma", "plasmoids")
        for d in [data_home, *data_dirs.split(":")]
        if d
    ]


def is_plasmoid_installed(plugin_id: str) -> bool:
    return any(
        os.path.isfile(os.path.join(d, plugin_id, "metadata.json"))
        for d in plasmoid_dirs()
    )


def is_plasmoid_in_panel(plugin_id: str) -> bool:
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    path = os.path.join(config_home, "plasma-org.kde.plasma.desktop-appletsrc")
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return any(line.strip() == f"plugin={plugin_id}" for line in f)
    except OSError:
        return False


def tree_sha256(root: str) -> str:
    """Hash every regular file below root (relative path + content).

    Independent of archive compression and timestamps, so it stays stable
    even if the hosting service re-packs the tarball."""
    digest = hashlib.sha256()
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            entries.append(os.path.relpath(full, root))
    for rel in sorted(entries):
        with open(os.path.join(root, rel), "rb") as f:
            content_hash = hashlib.sha256(f.read()).hexdigest()
        digest.update(rel.encode("utf-8") + b"\0" + content_hash.encode() + b"\n")
    return digest.hexdigest()


def validate_plasmoid_dir(path: str, plugin_id: str) -> str:
    """Return an error message, or "" if path holds the expected widget."""
    try:
        with open(os.path.join(path, "metadata.json"), encoding="utf-8") as f:
            metadata = json.load(f)
    except (OSError, ValueError):
        return "metadata.json is missing or invalid"
    if metadata.get("KPlugin", {}).get("Id") != plugin_id:
        return "unexpected plugin id"
    if metadata.get("KPackageStructure") != "Plasma/Applet":
        return "not a Plasma widget"
    if not str(metadata.get("X-Plasma-API-Minimum-Version", "")).startswith("6"):
        return "not compatible with Plasma 6"
    if not os.path.isfile(os.path.join(path, "contents", "ui", "main.qml")):
        return "contents/ui/main.qml is missing"
    return ""


class PlasmoidInstallJob(InstallJob):
    """Download, verify and install a pinned Plasma widget for this user.

    No administrator rights are needed: kpackagetool6 installs into
    ~/.local/share/plasma/plasmoids."""

    # Overridable by tests
    package_root: str | None = None
    kpackagetool = "kpackagetool6"

    def __init__(self, source: PlasmoidSource, label: str) -> None:
        super().__init__(label)
        self.source = source

    def _run(self) -> tuple[JobState, Failure]:
        if not shutil.which(self.kpackagetool):
            self._log(_("kpackagetool6 was not found."))
            return JobState.FAILED, Failure.UNSUPPORTED

        with tempfile.TemporaryDirectory(prefix="biglinux-welcome-") as tmp:
            archive = os.path.join(tmp, "source.tar.gz")
            self._progress(0.05, _("Downloading packages…"))
            self._log(f"GET {self.source.url}")
            result = self._download(archive)
            if result is not None:
                return result

            self._set_cancellable(False)
            self._progress(0.60, _("Verifying integrity…"))
            package_dir, error = self._extract(archive, os.path.join(tmp, "src"))
            if error:
                self._log(f"error: {error}")
                return JobState.FAILED, Failure.INTEGRITY

            digest = tree_sha256(package_dir)
            self._log(f"sha256 (tree): {digest}")
            if digest != self.source.tree_sha256:
                self._log(f"error: expected {self.source.tree_sha256}")
                return JobState.FAILED, Failure.INTEGRITY
            error = validate_plasmoid_dir(package_dir, self.source.plugin_id)
            if error:
                self._log(f"error: {error}")
                return JobState.FAILED, Failure.INTEGRITY

            self._progress(0.85, _("Installing…"))
            return self._install(package_dir)

    def _download(self, dest: str) -> tuple[JobState, Failure] | None:
        request = urllib.request.Request(
            self.source.url, headers={"User-Agent": "biglinux-welcome"}
        )
        try:
            with (
                urllib.request.urlopen(request, timeout=30) as resp,
                open(dest, "wb") as out,
            ):
                total = int(resp.headers.get("Content-Length") or 0)
                received = 0
                while True:
                    if self.cancel_requested:
                        return JobState.CANCELLED, Failure.NONE
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    received += len(chunk)
                    if received > self.source.max_bytes:
                        self._log("error: download is larger than expected")
                        return JobState.FAILED, Failure.INTEGRITY
                    out.write(chunk)
                    if total:
                        self._progress(
                            0.05 + 0.5 * received / total, _("Downloading packages…")
                        )
            self._log(_("Downloaded {size}").format(size=format_size(received)))
        except (OSError, ValueError) as e:
            self._log(f"error: {e}")
            return JobState.FAILED, Failure.NETWORK
        return None

    @staticmethod
    def _extract(archive: str, dest: str) -> tuple[str, str]:
        """Safely extract archive; return (package_dir, error)."""
        try:
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(dest, filter="data")
        except (tarfile.TarError, OSError, ValueError) as e:
            return "", str(e)
        entries = os.listdir(dest)
        if len(entries) != 1 or not os.path.isdir(os.path.join(dest, entries[0])):
            return "", "unexpected archive layout"
        return os.path.join(dest, entries[0]), ""

    def _kpackage(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [self.kpackagetool, "--type", "Plasma/Applet", *args]
        if self.package_root:
            cmd += ["--packageroot", self.package_root]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=120,
            check=False,
        )

    def _is_installed(self) -> bool:
        if self.package_root:
            return os.path.isfile(
                os.path.join(self.package_root, self.source.plugin_id, "metadata.json")
            )
        return is_plasmoid_installed(self.source.plugin_id)

    def _install(self, package_dir: str) -> tuple[JobState, Failure]:
        action = "--upgrade" if self._is_installed() else "--install"
        try:
            result = self._kpackage(action, package_dir)
        except (OSError, subprocess.TimeoutExpired) as e:
            self._log(f"error: {e}")
            return JobState.FAILED, Failure.UNKNOWN
        for line in (result.stdout + result.stderr).splitlines():
            if line.strip():
                self._log(line)
        if result.returncode != 0:
            return JobState.FAILED, Failure.UNKNOWN

        # Never trust the exit code alone: ask Plasma's package system
        # (--list honours --packageroot, unlike --show)
        try:
            listed = self._kpackage("--list")
        except (OSError, subprocess.TimeoutExpired):
            listed = None
        registered = listed is not None and any(
            line.strip() == self.source.plugin_id for line in listed.stdout.splitlines()
        )
        if not registered or not self._is_installed():
            return JobState.FAILED, Failure.VERIFICATION
        self._progress(1.0, _("Installed"))
        return JobState.SUCCEEDED, Failure.NONE


def add_plasmoid_to_panel(plugin_id: str) -> str:
    """Add a widget to the first Plasma panel. Returns an error or ""."""
    if not re.match(r"^[A-Za-z0-9._-]+$", plugin_id):
        return "invalid plugin id"
    script = (
        "var p = panels();"
        "if (p.length === 0) { throw new Error('no panel'); }"
        "var wasLocked = locked; locked = false;"
        f"p[0].addWidget('{plugin_id}');"
        "locked = wasLocked;"
    )
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
        bus.call_sync(
            "org.kde.plasmashell",
            "/PlasmaShell",
            "org.kde.PlasmaShell",
            "evaluateScript",
            GLib.Variant("(s)", (script,)),
            None,
            Gio.DBusCallFlags.NONE,
            10000,
            None,
        )
    except GLib.Error as e:
        return e.message
    return ""


# ---------------------------------------------------------------------------
# Single transaction at a time
# ---------------------------------------------------------------------------


class InstallManager(GObject.Object):
    """Make sure only one installation runs at a time, app-wide."""

    __gsignals__: ClassVar[dict] = {
        "busy-changed": (GObject.SignalFlags.RUN_LAST, None, (bool,)),
    }

    _default: InstallManager | None = None

    def __init__(self) -> None:
        super().__init__()
        self.current: InstallJob | None = None

    @classmethod
    def get_default(cls) -> InstallManager:
        if cls._default is None:
            cls._default = cls()
        return cls._default

    @property
    def busy(self) -> bool:
        return self.current is not None and self.current.state in (
            JobState.PENDING,
            JobState.RUNNING,
        )

    def start(self, job: InstallJob) -> bool:
        if self.busy:
            return False
        self.current = job
        job.connect("finished", self._on_finished)
        job.start()
        self.emit("busy-changed", True)
        return True

    def _on_finished(self, job: InstallJob) -> None:
        if job is self.current:
            self.current = None
            self.emit("busy-changed", False)
