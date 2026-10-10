#!/bin/bash

# Default browser helpers (run as the user).
# Installation goes through scripts/package-install.sh (see install_backend.py).

getDefaultBrowser() {
  xdg-settings get default-web-browser
}

setDefaultBrowser() {
  xdg-mime default "$1" x-scheme-handler/http
  xdg-mime default "$1" x-scheme-handler/https
  xdg-settings set default-web-browser "$1"
}

case "$1" in
    "getBrowser")
        getDefaultBrowser
        ;;
    "setBrowser")
        setDefaultBrowser "$2"
        ;;
    *)
        echo "Use: $0 {getBrowser|setBrowser <file.desktop>}"
        exit 1
        ;;
esac
