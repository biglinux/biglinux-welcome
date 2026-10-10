#!/usr/bin/env python3
"""BigLinux Welcome — Entry point."""

from __future__ import annotations

import gettext
import locale
import sys

# Internationalization
DOMAIN = "biglinux-welcome"
LOCALE_DIR = "/usr/share/locale"
try:
    locale.setlocale(locale.LC_ALL, "")
except locale.Error:
    # LANG names a locale that is not generated: keep the C locale (gettext
    # still follows LANGUAGE/LANG) instead of failing to start
    pass
locale.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.textdomain(DOMAIN)

from app import BigLinuxWelcomeApp


def main() -> None:
    """Entry point."""
    if "--version" in sys.argv:
        from utils import APP_NAME, APP_VERSION

        print(f"{APP_NAME} {APP_VERSION}")
        return

    start_page = 0
    if "--start-page" in sys.argv:
        try:
            idx = sys.argv.index("--start-page") + 1
            start_page = int(sys.argv[idx])
            # Remove the flag from argv so it doesn't confuse Gtk.Application.run
            del sys.argv[idx - 1 : idx + 1]
        except (ValueError, IndexError):
            pass

    app = BigLinuxWelcomeApp(start_page=start_page)
    app.run(sys.argv)


if __name__ == "__main__":
    main()
