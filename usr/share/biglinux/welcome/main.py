#!/usr/bin/env python3
"""BigLinux Welcome — Entry point."""

from __future__ import annotations

import gettext
import locale
import sys

# Internationalization
DOMAIN = "biglinux-welcome"
LOCALE_DIR = "/usr/share/locale"
locale.setlocale(locale.LC_ALL, "")
locale.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.bindtextdomain(DOMAIN, LOCALE_DIR)
gettext.textdomain(DOMAIN)

from app import BigLinuxWelcomeApp


def main() -> None:
    """Entry point."""
    start_page = 0
    if "--start-page" in sys.argv:
        try:
            idx = sys.argv.index("--start-page") + 1
            start_page = int(sys.argv[idx])
            # Remove the flag from argv so it doesn't confuse Gtk.Application.run
            sys_arg_to_remove = sys.argv[idx]
            sys.argv.pop(idx)
            sys.argv.pop(idx - 1)
        except (ValueError, IndexError):
            pass

    app = BigLinuxWelcomeApp(start_page=start_page)
    app.run(sys.argv)


if __name__ == "__main__":
    main()
