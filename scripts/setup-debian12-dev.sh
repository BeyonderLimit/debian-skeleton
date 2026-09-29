#!/usr/bin/env bash
#
# Debian 12 developer workstation bootstrap.
# Run as:
#   sudo bash setup-dev-debian12.sh <developer-username>
#
# Example:
#   sudo bash setup-dev-debian12.sh alice
#

set -Eeuo pipefail
IFS=$'\n\t'

readonly SCRIPT_NAME="${0##*/}"
readonly NVM_VERSION="v0.40.8"

log() {
    printf '\n==> %s\n' "$*"
}

warn() {
    printf '\nWARNING: %s\n' "$*" >&2
}

die() {
    printf '\nERROR: %s\n' "$*" >&2
    exit 1
}

on_error() {
    local exit_code=$?
    printf '\nERROR: %s failed at line %s (exit code: %s)\n' \
        "$SCRIPT_NAME" "$1" "$exit_code" >&2
    exit "$exit_code"
}

trap 'on_error $LINENO' ERR

require_root() {
    if [[ "${EUID}" -ne 0 ]]; then
        die "Run this script with sudo or as root."
    fi
}

validate_developer_user() {
    local user="$1"

    [[ -n "$user" ]] || die "Usage: sudo bash $SCRIPT_NAME <developer-username>"

    if ! id "$user" >/dev/null 2>&1; then
        die "User '$user' does not exist."
    fi

    if [[ "$user" == "root" ]]; then
        die "Use a non-root login user for developer tools such as nvm."
    fi

    DEVELOPER_USER="$user"
    DEVELOPER_HOME="$(getent passwd "$DEVELOPER_USER" | cut -d: -f6)"

    [[ -d "$DEVELOPER_HOME" ]] || die "Home directory '$DEVELOPER_HOME' does not exist."
}

verify_debian_12() {
    source /etc/os-release

    if [[ "${ID}" != "debian" || "${VERSION_ID}" != "12" ]]; then
        die "This script supports Debian 12 only. Detected: ${PRETTY_NAME:-unknown}"
    fi
}

update_system() {
    log "Updating package lists and installed packages"

    export DEBIAN_FRONTEND=noninteractive

    apt-get update
    apt-get upgrade -y
    apt-get autoremove -y
}

install_base_packages() {
    log "Installing core development tools and utilities"

    apt-get install -y \
        apt-transport-https \
        build-essential \
        ca-certificates \
        curl \
        devscripts \
        fakeroot \
        git \
        gnupg \
        htop \
        pass \
        pkg-config \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        tmux \
        ufw \
        unzip \
        vim \
        wget \
        shellcheck \
    	jq \
    	ripgrep \
    	fd-find \
    	make \
    	pkg-config \
    	sqlite3 \
    	postgresql-client \
    	libssl-dev \
    	libffi-dev libcurl4-openssl-dev libsdl2-dev \
        zip
}

install_node_for_developer() {
    log "Installing nvm and Node.js LTS for ${DEVELOPER_USER}"

    sudo -u "$DEVELOPER_USER" -H bash <<EOF
set -Eeuo pipefail

export HOME="$DEVELOPER_HOME"
export NVM_DIR="\$HOME/.nvm"

curl --fail --show-error --silent --location \
    "https://raw.githubusercontent.com/nvm-sh/nvm/${NVM_VERSION}/install.sh" | bash

source "\$NVM_DIR/nvm.sh"

nvm install --lts
nvm alias default 'lts/*'
nvm use default

corepack enable

node --version
npm --version
EOF
}

install_docker() {
    log "Installing Docker Engine from Docker's official APT repository"

    install -m 0755 -d /etc/apt/keyrings

    curl --fail --show-error --silent --location \
        https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc

    chmod a+r /etc/apt/keyrings/docker.asc

    cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: $(. /etc/os-release && echo "$VERSION_CODENAME")
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

    apt-get update

    apt-get install -y \
        containerd.io \
        docker-buildx-plugin \
        docker-ce \
        docker-ce-cli \
        docker-compose-plugin

    systemctl enable --now docker

    usermod -aG docker "$DEVELOPER_USER"

    docker --version
    docker compose version
}

install_vscodium() {
    log "Installing VSCodium from its APT repository"

    curl --fail --show-error --silent --location \
        https://gitlab.com/paulcarroty/vscodium-deb-rpm-repo/raw/master/pub.gpg \
        | gpg --dearmor \
        | tee /usr/share/keyrings/vscodium-archive-keyring.gpg > /dev/null

    chmod a+r /usr/share/keyrings/vscodium-archive-keyring.gpg

    cat > /etc/apt/sources.list.d/vscodium.list <<EOF
deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/vscodium-archive-keyring.gpg] https://download.vscodium.com/debs vscodium main
EOF

    apt-get update
    apt-get install -y codium
}

configure_ufw() {
    log "Configuring UFW"

    # Avoid locking yourself out of a remotely administered machine.
    if systemctl is-active --quiet ssh || systemctl is-active --quiet sshd; then
        ufw allow OpenSSH
    fi

    ufw default deny incoming
    ufw default allow outgoing

    # Do NOT open web/development ports by default.
    # Add only services deliberately exposed by this host, for example:
    # ufw allow 3000/tcp

    ufw --force enable
    ufw status verbose
}

show_summary() {
    log "Developer environment setup completed"

    cat <<EOF

Installed:
  - Core build tools, Python, Git, utilities
  - nvm and current Node.js LTS for: $DEVELOPER_USER
  - Docker Engine, Buildx, and Docker Compose plugin
  - VSCodium
  - UFW with incoming traffic denied by default

Required next steps:
  1. Log out and log back in as $DEVELOPER_USER.
     This activates the new docker group membership.

  2. Verify Docker without sudo:
       docker run --rm hello-world

  3. Verify Node:
       node --version
       npm --version

Security note:
  Membership in the docker group is effectively root-level access.
  Only add trusted local accounts to that group.

EOF
}

main() {
    require_root
    validate_developer_user "${1:-}"
    verify_debian_12

    log "Starting Debian 12 developer environment setup for ${DEVELOPER_USER}"

    update_system
    install_base_packages
    install_node_for_developer
    install_docker
    install_vscodium
    configure_ufw
    show_summary
}

main "$@"
