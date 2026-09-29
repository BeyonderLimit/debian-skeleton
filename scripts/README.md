# Debian Skeleton Shell Scripts

## Debian 12 Developer Script

A safer Debian 12 developer bootstrap script, followed by a detailed patch review and suggested changes. It follows Docker’s current Debian repository setup and VSCodium’s Debian 12 repository instructions.

### script

review the variables, then run:

```bash

sudo bash setup-debian12-dev.sh <your-login-username>
```

## Important considerations

### 1. Do not run developer tooling as root

The original root check makes sense for package and service installation, but nvm is specifically a per-user Node version manager. If installed as root, it configures /root/.nvm and the normal login account will not have nvm, node, or npm on its path.

The revised script separates responsibilities:

    Root installs system packages, configures APT repositories, Docker, and UFW.

    The named developer account receives nvm and Node.js.

    Docker group membership is applied to that developer account.

If you have multiple local developers, either run the nvm section once for each user or favor a system-managed Node installation through Debian or NodeSource. For a single personal workstation, nvm is usually convenient because projects can select different Node releases.

### 2. Docker group access is privileged

docker group membership is not merely a convenience. A member can typically mount host paths into privileged containers, access the Docker socket, and effectively obtain root-equivalent control of the machine. Treat it as an administrative group.

For a laptop used by one trusted developer, adding the developer to docker is normal. For shared systems, CI runners, or remotely accessed hosts, consider Docker’s rootless mode instead, and avoid making broad user groups Docker members. Docker’s Debian installation documentation covers the repository-backed installation approach used here.

### 3. Do not expose dev ports by default

Your original UFW rules expose:

   	- TCP 80

    - TCP 443

    - TCP 3000

That is appropriate only if the machine intentionally hosts a web service accessible from the network. On a workstation:

    Bind local development servers to 127.0.0.1 or localhost.

    Use SSH port forwarding, a reverse proxy, or a deliberate firewall rule when remote testing is required.

    Open only a required port, for only the required network or IP range when possible.

For example, if a temporary service must be reachable only from a LAN subnet, a narrower rule is safer than opening it globally:

```bash

ufw allow from 192.168.1.0/24 to any port 3000 proto tcp
```

**Do not apply that exact subnet unless it matches your network.**

### 4. Plan how upgrades should behave

The script uses apt-get upgrade -y, which is reasonable for a newly provisioned workstation. However, broad unattended upgrades can occasionally defer packages or leave kernel-related cleanup for later.

Possible improvements:

    Use apt-get full-upgrade -y only if you deliberately want package additions/removals required by dependency transitions.

    Configure unattended-upgrades for security updates.

    Reboot when the installed kernel or critical libraries require it.

    Keep a snapshot, backup, or rollback plan before using this on an established development machine.

A practical post-upgrade check is:

```bash

test -f /var/run/reboot-required && echo "Reboot required"
```
Debian does not universally create this marker in every reboot-worthy situation, so also check the package manager’s output and whether the running kernel differs from the newly installed one.

## Ukui Minimal installer

A display manager normally starts the selected desktop session; startx is an alternative for a TTY-only workflow, but it needs an installed X stack and a correct user session command. UKUI’s own session manager is intended to be started by a display manager such as LightDM.

### Revised minimal UKUI script

This version supports two modes:

   - Default: install LightDM and the UKUI greeter for normal graphical logins. This is the recommended desktop approach.

   - STARTX_ONLY=1: install Xorg and xinit, write ~/.xinitrc, and allow the specified user to start UKUI from a TTY using startx.

### Run it as:

```bash

sudo bash ukui-minimal.sh your-login-name
```
For a startx-only system:

```bash

sudo STARTX_ONLY=1 bash ukui-minimal.sh your-login-name
```
