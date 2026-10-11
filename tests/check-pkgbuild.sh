#!/bin/bash
# Check pkgbuild/PKGBUILD the way the BigLinux package builder uses it.
#   tests/check-pkgbuild.sh build DIR     as a normal user: build this tree into DIR
#   tests/check-pkgbuild.sh install DIR   as root, on a disposable system only:
#                                         install, verify and remove the package
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."
root=$PWD
pkgname=biglinux-welcome
work=

fail() {
    echo "error: $*" >&2
    exit 1
}

build() {
    local out
    out=$(mkdir -p "$1" && readlink -f "$1")
    work=$(mktemp -d)
    trap 'rm -rf "$work"' EXIT

    # The builder (gitlab.bigib.org/builder/packagebuilder, file package-build)
    # edits the PKGBUILD before building: it pins the source to the branch that
    # requested the build, turns arch=('any') into x86_64/aarch64 and adds git
    # to makedepends. The result must still parse and point to the right source.
    cp pkgbuild/PKGBUILD "$work/"
    sed -i '/source=/s/\.git"/\.git#branch=main"/' "$work/PKGBUILD"
    sed -i "/\barch=/s/arch=.*/arch=('x86_64' 'aarch64')/" "$work/PKGBUILD"
    sed -i "/makedepends=/s/(/\('git\' /" "$work/PKGBUILD"
    (cd "$work" && makepkg --printsrcinfo) >"$work/SRCINFO"
    grep -qx $'\tsource = git+https://github.com/biglinux/biglinux-welcome.git#branch=main' "$work/SRCINFO" ||
        fail "the builder's rewrite of source= no longer matches; see $work/SRCINFO"
    grep -qx $'\tarch = x86_64' "$work/SRCINFO" || fail "the builder's rewrite of arch= no longer matches"
    echo "PKGBUILD as rewritten by the builder:"
    grep -E '^\s*(pkgver|pkgrel|epoch|arch|source) =' "$work/SRCINFO"

    # Build this checkout, not the published repository
    (cd pkgbuild && BIGLINUX_WELCOME_SRC="$root" BUILDDIR="$work/build" PKGDEST="$out" \
        makepkg --nodeps --noconfirm --cleanbuild --force)

    # namcap warnings are informative; errors fail the check
    local report
    report=$(namcap pkgbuild/PKGBUILD "$out"/"$pkgname"-*.pkg.tar.*)
    echo "$report"
    ! grep -q ' E: ' <<<"$report" || fail "namcap reported errors"
}

install() {
    local pkg
    [ "$EUID" -eq 0 ] || fail "install needs root (use a disposable container)"
    pkg=$(find "$1" -maxdepth 1 -name "$pkgname-*.pkg.tar.*" ! -name '*.sig' | head -n1)
    [ -n "$pkg" ] || fail "no package in $1"

    # Dependencies come from the configured repositories
    pacman -U --noconfirm "$pkg"
    pacman -Qkk "$pkgname"

    test -x /usr/bin/biglinux-welcome || fail "launcher not executable"
    [ "$(stat -c %a /usr/share/biglinux/welcome/scripts/package-install.sh)" = 755 ] ||
        fail "privileged helper must be mode 755"
    if pacman -Qlq "$pkgname" | grep -E '__pycache__|\.ruff_cache|\.pytest_cache|/tests/|/docs/'; then
        fail "development files in the package"
    fi
    pacman -Qlq "$pkgname" | grep '\.py$' |
        xargs python3 -c 'import ast, sys; [ast.parse(open(f).read(), f) for f in sys.argv[1:]]'
    test -L /etc/systemd/user/graphical-session.target.wants/biglinux-welcome.service ||
        fail "post_install did not enable the user service"
    python3 /usr/share/biglinux/welcome/main.py --version

    pacman -R --noconfirm "$pkgname"
    ! test -e /usr/bin/biglinux-welcome || fail "files left after removal"
    ! test -e /etc/systemd/user/graphical-session.target.wants/biglinux-welcome.service ||
        fail "pre_remove did not disable the user service"
    echo "install, verification and removal passed"
}

case "${1:-}" in
build | install)
    [ -n "${2:-}" ] || fail "usage: $0 build|install DIR"
    "$1" "$2"
    ;;
*) fail "usage: $0 build|install DIR" ;;
esac
