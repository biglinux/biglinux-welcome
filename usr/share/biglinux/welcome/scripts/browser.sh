#!/bin/bash

getDefaultBrowser() {
  xdg-settings get default-web-browser
#   xdg-mime query default x-scheme-handler/http
}

setDefaultBrowser() {
  xdg-mime default "$1" x-scheme-handler/http
  xdg-mime default "$1" x-scheme-handler/https
  xdg-settings set default-web-browser "$1"
}

# change the state
installBrowser() {
  local script_dir
  script_dir="$(dirname "$(readlink -f "$0")")"
  pkexec "$script_dir/browserInstall.sh" "$1"
  exitCode=$?
  exit $exitCode
}

# Executes the function based on the parameter
case "$1" in
    # "check")
    #     checkBrowserState "$2"
    #     ;;
    "install")
        installBrowser "$2"
        ;;
    "getBrowser")
        getDefaultBrowser
        ;;
    "setBrowser")
        setDefaultBrowser "$2"
        ;;
    *)
        echo "Use: $0 {check|install} [true|false]"
        echo "  check          - Check current status"
        echo "  install        - install the specified browser"
        exit 1
        ;;
esac
