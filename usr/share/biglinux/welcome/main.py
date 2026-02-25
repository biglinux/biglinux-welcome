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

from app import BigLinuxWelcomeApp  # noqa: E402


def main() -> None:
    """Entry point."""
    app = BigLinuxWelcomeApp()
    app.run(sys.argv)


if __name__ == "__main__":
    main()
