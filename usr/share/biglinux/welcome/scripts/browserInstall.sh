#!/bin/bash

#Translation
export TEXTDOMAINDIR="/usr/share/locale"
export TEXTDOMAIN=biglinux-welcome

# Assign the received arguments to variables with clear names
browser="$1"
originalUser="$2"
userDisplay="$3"
userXauthority="$4"
userDbusAddress="$5"
userLang="$6"
userLanguage="$7"

# Helper browser to run a command as the original user
runAsUser() {
	# Single quotes around variables are a good security practice
	su "$originalUser" -c "export DISPLAY='$userDisplay'; export XAUTHORITY='$userXauthority'; export DBUS_SESSION_BUS_ADDRESS='$userDbusAddress'; export LANG='$userLang'; export LC_ALL='$userLang'; export LANGUAGE='$userLanguage'; $1"
}

# 1. Creates a named pipe (FIFO) for communication with Zenity
pipePath="/tmp/browser_install_pipe_$$"
mkfifo "$pipePath"

# 2. Starts Zenity IN THE BACKGROUND, as the user, with the full environment
zenityTitle=$"Browser Install"
zenityText=$"Installing Browser, Please wait..."
runAsUser "zenity --progress --title=\"$zenityTitle\" --text=\"$zenityText\" --pulsate --auto-close --no-cancel < '$pipePath'" &

# 3. Executes the root tasks.
installBrowser() {
	log="/var/log/biglinux-welcome.log"
	echo "" >>$log
	date >>$log
	if [[ "$browser" == "brave" ]]; then
		pacman -Syu --noconfirm brave >>$log 2>&1
	elif [[ "$browser" == "chromium" ]]; then
		pacman -Syu --noconfirm chromium >>$log 2>&1
	elif [[ "$browser" == "google-chrome" ]]; then
		yay -Syu --noconfirm google-chrome >>$log 2>&1
	elif [[ "$browser" == "falkon" ]]; then
		pacman -Syu --noconfirm falkon >>$log 2>&1
	elif [[ "$browser" == "firefox" ]]; then
		pacman -Syu --noconfirm firefox >>$log 2>&1
	elif [[ "$browser" == "librewolf" ]]; then
		yay -Syu --noconfirm librewolf-bin >>$log 2>&1
	elif [[ "$browser" == "opera" ]]; then
		yay -Syu --noconfirm opera 2>&1 >>$log 2>&1
	elif [[ "$browser" == "vivaldi" ]]; then
		pacman -Syu --noconfirm vivaldi 2>&1 >>$log 2>&1
	elif [[ "$browser" == "edge" ]]; then
		yay -Syu --noconfirm microsoft-edge-stable-bin >>$log 2>&1
	elif [[ "$browser" == "zen-browser" ]]; then
		yay -Syu --noconfirm zen-browser-bin 2>&1 >>$log 2>&1
	fi
	exitCode=$?
}
installBrowser >"$pipePath"

# 4. Cleans up the pipe
rm "$pipePath"

# 5. Shows the final result to the user, also with the correct theme.
if [[ "$exitCode" -eq 0 ]]; then
	zenityText=$"Browser installed successfully!"
	runAsUser "zenity --info --text=\"$zenityText\""
else
	zenityText=$"An error occurred while install browser."
	runAsUser "zenity --error --text=\"$zenityText\""
fi

# 6. Exits the script with the correct exit code
exit $exitCode
