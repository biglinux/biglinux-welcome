#!/bin/bash

# Detect the current desktop environment
if pgrep -x plasmashell >/dev/null; then
    # KDE Plasma
    # Try systemsettings first (more stable), fallback to alternatives
    systemsettings kcm_kscreen 2>/dev/null || systemsettings5 kcm_screen 2>/dev/null || kcmshell6 kcm_kscreen 2>/dev/null || kscreen-doctor-settings 2>/dev/null
elif pgrep -x gnome-shell >/dev/null; then
    # GNOME
    gnome-control-center display 2>/dev/null
elif pgrep -x xfce4-session >/dev/null; then
    # XFCE
    xfce4-display-settings 2>/dev/null || arandr 2>/dev/null
elif pgrep -x cinnamon-session >/dev/null; then
    # Cinnamon
    cinnamon-settings display 2>/dev/null
else
    # Generic fallback
    if command -v arandr >/dev/null; then
        arandr
    elif command -v xrandr >/dev/null; then
        echo "Use 'xrandr' for display settings via terminal"
    else
        echo "Could not open display settings"
    fi
fi
