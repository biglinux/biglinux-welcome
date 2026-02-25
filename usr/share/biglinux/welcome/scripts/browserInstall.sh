#!/bin/bash

# Browser installation script (runs as root via pkexec).
# All output goes to stdout/stderr for the calling application to display.
# No Zenity or GUI — the welcome app handles the UI.

browser="$1"
log="/var/log/biglinux-welcome.log"

# Force English output so progress parsing works regardless of system locale
export LANGUAGE=C
export LC_ALL=C

echo "" >> "$log"
date >> "$log"

echo "STATUS:started"
echo "Preparing $browser..."

case "$browser" in
	brave)
		stdbuf -o0 pacman -Sy --noconfirm brave 2>&1 | stdbuf -o0 tee -a "$log" ;;
	chromium)
		stdbuf -o0 pacman -Sy --noconfirm chromium 2>&1 | stdbuf -o0 tee -a "$log" ;;
	google-chrome)
		stdbuf -o0 yay -Sy --noconfirm google-chrome 2>&1 | stdbuf -o0 tee -a "$log" ;;
	falkon)
		stdbuf -o0 pacman -Sy --noconfirm falkon 2>&1 | stdbuf -o0 tee -a "$log" ;;
	firefox)
		stdbuf -o0 pacman -Sy --noconfirm firefox 2>&1 | stdbuf -o0 tee -a "$log" ;;
	librewolf)
		stdbuf -o0 yay -Sy --noconfirm librewolf-bin 2>&1 | stdbuf -o0 tee -a "$log" ;;
	opera)
		stdbuf -o0 yay -Sy --noconfirm opera 2>&1 | stdbuf -o0 tee -a "$log" ;;
	vivaldi)
		stdbuf -o0 pacman -Sy --noconfirm vivaldi 2>&1 | stdbuf -o0 tee -a "$log" ;;
	edge)
		stdbuf -o0 yay -Sy --noconfirm microsoft-edge-stable-bin 2>&1 | stdbuf -o0 tee -a "$log" ;;
	zen-browser)
		stdbuf -o0 yay -Sy --noconfirm zen-browser-bin 2>&1 | stdbuf -o0 tee -a "$log" ;;
	*)
		echo "Unknown browser: $browser" | tee -a "$log"
		exit 1 ;;
esac

exitCode=${PIPESTATUS[0]}

if [[ "$exitCode" -eq 0 ]]; then
	echo "STATUS:success"
else
	echo "STATUS:error"
fi

exit $exitCode
