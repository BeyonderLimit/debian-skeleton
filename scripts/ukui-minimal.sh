#!/usr/bin/env bash
#
# Minimal UKUI desktop setup for Debian 12.
#
# Run:
#   sudo bash install-ukui-minimal.sh <login-user>
#
# Optional startx-only mode:
#   sudo STARTX_ONLY=1 bash install-ukui-minimal.sh <login-user>
#
sudo apt-get update

sudo apt-get install -y --no-install-recommends \
  xinit \
  xserver-xorg \
  xserver-xorg-core \
  xserver-xorg-input-libinput \
  x11-xserver-utils \
  x11-xinit \
  xterm \
  dbus-x11 \
  dbus-user-session \
  policykit-1 \
  ukui-session-manager \
  ukui-settings-daemon \
  ukui-panel \
  ukui-menu \
  ukui-control-center \
  ukui-power-manager \
  ukui-window-switch \
  ukui-media \
  ukui-themes \
  ukui-wallpapers \
  peony

  echo 
echo ukui install complete, please reboot and issue 'exec dbus-run-session ukui-session'
echo
