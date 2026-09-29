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

set -Eeuo pipefail
IFS=$'\n\t'

readonly SCRIPT_NAME="${0##*/}"
readonly STARTX_ONLY="${STARTX_ONLY:-0}"

log() {
    printf '\n==> %s\n' "$*"
}

die() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

on_error() {
    local exit_code=$?
    printf '\nERROR: %s failed at line %s (exit code %s)\n' \
        "$SCRIPT_NAME" "$1" "$exit_code" >&2
    exit "$exit_code"
}

trap 'on_error $LINENO' ERR

require_root() {
    [[ "$EUID" -eq 0 ]] || die "Run this script with sudo or as root."
}

validate_os() {
    source /etc/os-release

    if [[ "${ID:-}" != "debian" || "${VERSION_ID:-}" != "12" ]]; then
        die "This script supports Debian 12 only. Detected: ${PRETTY_NAME:-unknown}"
    fi
}

validate_user() {
    local user="${1:-}"

    [[ -n "$user" ]] || die "Usage: sudo bash $SCRIPT_NAME <login-user>"
    id "$user" >/dev/null 2>&1 || die "User '$user' does not exist."
    [[ "$user" != "root" ]] || die "Specify a regular desktop user, not root."

    DEVELOPER_USER="$user"
    DEVELOPER_HOME="$(getent passwd "$DEVELOPER_USER" | cut -d: -f6)"

    [[ -n "$DEVELOPER_HOME" && -d "$DEVELOPER_HOME" ]] \
        || die "Could not determine a valid home directory for '$DEVELOPER_USER'."
}

update_apt() {
    log "Refreshing APT package metadata"
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
}

install_ukui_base() {
    log "Installing a minimal functional UKUI desktop"

    apt-get install -y --no-install-recommends \
        dbus-x11 \
        policykit-1 \
        xserver-xorg \
        ukui-control-center \
        ukui-media \
        ukui-menu \
        ukui-panel \
        ukui-power-manager \
        ukui-session-manager \
        ukui-settings-daemon \
        ukui-themes \
        ukui-wallpapers \
        ukui-window-switch \
        peony \
        peony-extensions
}

install_login_method() {
    if [[ "$STARTX_ONLY" == "1" ]]; then
        log "Installing startx support; no graphical display manager will be installed"

        apt-get install -y --no-install-recommends \
            xinit \
            xterm

        install -d -m 0755 -o "$DEVELOPER_USER" -g "$DEVELOPER_USER" \
            "$DEVELOPER_HOME"

        cat > "$DEVELOPER_HOME/.xinitrc" <<'EOF'
#!/bin/sh
exec ukui-session
EOF

        chown "$DEVELOPER_USER:$DEVELOPER_USER" "$DEVELOPER_HOME/.xinitrc"
        chmod 0755 "$DEVELOPER_HOME/.xinitrc"
    else
        log "Installing LightDM and the UKUI graphical login greeter"

        apt-get install -y --no-install-recommends \
            lightdm \
            ukui-greeter

        systemctl enable lightdm
    fi
}

install_removable_media_support() {
    log "Installing optional removable-media support"

    apt-get install -y --no-install-recommends \
        ntfs-3g \
        udisks2

    # Optional: uncomment if you specifically want udiskie automount behavior.
    # apt-get install -y --no-install-recommends udiskie
}

install_smb_client_only() {
    log "Installing SMB client support without enabling file sharing"

    apt-get install -y --no-install-recommends \
        smbclient
}

show_summary() {
    log "UKUI installation complete"

    if [[ "$STARTX_ONLY" == "1" ]]; then
        cat <<EOF

UKUI was configured for startx.

Log in on a local TTY as:
  $DEVELOPER_USER

Then start the desktop with:
  startx

The user session file is:
  $DEVELOPER_HOME/.xinitrc

EOF
    else
        cat <<EOF

UKUI and LightDM are installed.

Reboot, or start the display manager now with:
  sudo systemctl start lightdm

At the LightDM login screen, select the UKUI session if it is not selected
automatically.

EOF
    fi
}

main() {
    require_root
    validate_os
    validate_user "${1:-}"

    log "Installing UKUI for user: $DEVELOPER_USER"

    update_apt
    install_ukui_base
    install_login_method
    install_removable_media_support
    install_smb_client_only
    show_summary
}

main "$@"
