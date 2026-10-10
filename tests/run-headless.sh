#!/bin/bash
# Run the test suite, GUI tests included, on GTK's headless Broadway backend.
#   tests/run-headless.sh [pytest arguments...]
set -u
cd "$(dirname "$(readlink -f "$0")")/.." || exit 1

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-$(mktemp -d)}"
display=":${BROADWAY_TEST_DISPLAY:-55}"

gtk4-broadwayd "$display" >/dev/null 2>&1 &
broadway=$!
trap 'kill "$broadway" 2>/dev/null' EXIT
sleep 1

GDK_BACKEND=broadway BROADWAY_DISPLAY="$display" python -m pytest tests/ "$@"
