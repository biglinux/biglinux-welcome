#!/bin/bash
#
# BigLinux Welcome — privileged package installer (runs as root via pkexec).
#
# Usage:
#   package-install.sh install <package> [repository]
#       pacman -S --needed [repository/]<package>
#   package-install.sh upgrade-install <package> [repository]
#       pacman -Syu --needed [repository/]<package>
#
# Only packages in ALLOWED_PACKAGES, optionally pinned to a repository in
# ALLOWED_REPOSITORIES, can be installed (keep both in sync with install_backend.py). The welcome app shows the user the full transaction and asks
# for confirmation before calling this script, which is why pacman runs with
# --noconfirm: with it, pacman still refuses to remove conflicting packages.
#
# The parent process may write "cancel" to stdin; pacman then receives SIGINT,
# which it handles safely (it never stops in the middle of a package).
#
# Output is plain pacman output (LC_ALL=C) plus STATUS: lines for the app.
# Exit codes: 0 ok, 1 pacman failed, 2 usage/not allowed, 3 database locked,
#             4 not running as root.

set -u

readonly ALLOWED_PACKAGES=(
	biglinux-driver-manager
	biglinux-noise-reduction-pipewire
	tts-biglinux
	big-advogados
	bigame-mode
	big-remote-play
	bigcam
	biglinux-body-tracker
	brave-browser
	chromium
	falkon
	firefox
	librewolf
	vivaldi
	zen-browser-bin
)

readonly ALLOWED_REPOSITORIES=(
	biglinux-stable
)

readonly EXIT_FAILED=1
readonly EXIT_USAGE=2
readonly EXIT_LOCKED=3
readonly EXIT_NOT_ROOT=4

export LC_ALL=C LANG=C LANGUAGE=C

pacman_bin=/usr/bin/pacman
lock_file=/var/lib/pacman/db.lck
log_file=/var/log/biglinux-welcome.log

usage() {
	echo "Usage: $0 {install|upgrade-install} <package> [repository]" >&2
	exit "$EXIT_USAGE"
}

# is_in <value> <allowed values...>
is_in() {
	local value="$1" candidate
	shift
	for candidate in "$@"; do
		[[ "$value" == "$candidate" ]] && return 0
	done
	return 1
}

[[ $# -eq 2 || $# -eq 3 ]] || usage
mode="$1"
package="$2"
repository="${3:-}"

case "$mode" in
	install) pacman_args=(-S --needed --noconfirm) ;;
	upgrade-install) pacman_args=(-Syu --needed --noconfirm) ;;
	*) usage ;;
esac

if ! is_in "$package" "${ALLOWED_PACKAGES[@]}"; then
	echo "error: package not allowed: $package" >&2
	exit "$EXIT_USAGE"
fi

target="$package"
if [[ -n "$repository" ]]; then
	if ! is_in "$repository" "${ALLOWED_REPOSITORIES[@]}"; then
		echo "error: repository not allowed: $repository" >&2
		exit "$EXIT_USAGE"
	fi
	target="$repository/$package"
fi

if [[ $EUID -ne 0 ]]; then
	# Test mode: lets the test suite run this script unprivileged against a
	# fake pacman. Ignored as root, and pkexec never passes these variables.
	if [[ -n "${BIGLINUX_WELCOME_TEST:-}" ]]; then
		pacman_bin="${BIGLINUX_WELCOME_TEST_PACMAN:?}"
		lock_file="${BIGLINUX_WELCOME_TEST_LOCK:?}"
		log_file=/dev/null
	else
		echo "error: this script must run as root" >&2
		exit "$EXIT_NOT_ROOT"
	fi
fi

echo "STATUS:started"

if [[ -e "$lock_file" ]]; then
	echo "error: unable to lock database (another package manager is running)"
	echo "STATUS:error"
	exit "$EXIT_LOCKED"
fi

{ echo; date; echo "biglinux-welcome: pacman ${pacman_args[*]} -- $target"; } >>"$log_file" 2>/dev/null

# Keep stdin reachable for the cancel watcher (background jobs get /dev/null)
exec 3<&0

# Background jobs inherit an ignored SIGINT; env restores it so "cancel"
# works. tee -p keeps pacman alive even if the app closes its end of the pipe.
env --default-signal=INT stdbuf -oL "$pacman_bin" "${pacman_args[@]}" -- "$target" </dev/null \
	> >(stdbuf -oL tee -p -a "$log_file" 2>/dev/null) 2>&1 &
pacman_pid=$!

(
	while IFS= read -r -u 3 command; do
		if [[ "$command" == "cancel" ]]; then
			echo "Cancel requested"
			kill -INT "$pacman_pid" 2>/dev/null
		fi
	done
) &
watcher_pid=$!

wait "$pacman_pid"
exit_code=$?
kill "$watcher_pid" 2>/dev/null
wait "$watcher_pid" 2>/dev/null

if [[ $exit_code -eq 0 ]]; then
	echo "STATUS:success"
	exit 0
fi
echo "STATUS:error"
exit "$EXIT_FAILED"
