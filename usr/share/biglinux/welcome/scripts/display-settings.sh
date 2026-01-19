#!/bin/bash

# Detectar ambiente desktop
if pgrep -x plasmashell >/dev/null; then
    # KDE Plasma
    # Tenta abrir via systemsettings primeiro (mais estável), fallback para alternativas
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
    # Fallback genérico
    if command -v arandr >/dev/null; then
        arandr
    elif command -v xrandr >/dev/null; then
        echo "Use 'xrandr' para configurações de display via terminal"
    else
        echo "Não foi possível abrir as configurações de display"
    fi
fi
