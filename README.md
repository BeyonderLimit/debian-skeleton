# Debian Skeleton - Dress up your skeleton

A **TTY-first, post-install Debian configurator**: inspect the installed system, recommend a profile, show an exact plan, and apply it only after confirmation. I would keep it separate from building Debian installation images; image creation can become another backend later.


# Quickstart with xfce

# Debian Bookworm Xfce4 Minimal Install Guide

The standard Debian installation process for Xfce desktop includes additional packages that may not be necessary for many users. This guide will allow you to install a minimal Xfce desktop, adding additional packages as needed.

## Requirements

    A debian installation (hardware or virtual machine) with appropriate video drivers.

    sudo privileges to install packages and run optional install script.

    Installation of git to clone this repo sudo pkg install git

    Installation of bash to run install script sudo pkg install bash

## ISO for Installing Debian

Info for Debian installs : [debian-12.15.0-amd64-netinst.iso](https://cdimage.debian.org/cdimage/archive/12.15.0/amd64/iso-cd/debian-12.15.0-amd64-netinst.iso), 
[Installing Debian 12](https://www.debian.org/releases/bookworm/debian-installer/) , 
[Debian “bookworm” Release Information](https://www.debian.org/releases/bookworm/)



Uncheck Debian **desktop environment** to install a minimal debian system.

## Update sources to testing or unstable (optional)
Update sources to bookworm. The current testing branch.
```
sudo nano /etc/apt/sources:
```
```
deb http://deb.debian.org/debian/ bookworm main
#deb-src http://deb.debian.org/debian/ bookworm main

deb http://security.debian.org/debian-security bookworm-security main
#deb-src http://security.debian.org/debian-security bookworm-security main

deb http://deb.debian.org/debian/ bookworm-updates main
#deb-src http://deb.debian.org/debian/ bookworm-updates main
```

Add contrib non-free-firmware after each main entry if you need special drivers or additional firmware.

The other option would be debian sid. Update sources as follows:
```
deb http://deb.debian.org/debian/ unstable main
#deb-src http://deb.debian.org/debian/ unstable main
```

## Upgrade your system:

```
su -

apt update && apt upgrade

apt install -y curl git wget build-essential sudo synaptic python3.11-venv python3-venv python3-dev make cmake gcc g++ meson 
```

## Sudo Permission control
```
sudo visudo
```
## Basic Syntax Structure
When you add a rule inside the file, it typically follows this pattern:
username   host=(run_as_user:run_as_group)  

- Example (Full Root Permissions):
```
john  ALL=(ALL:ALL) ALL 
```
- Example (No Password Required):
```text
john  ALL=(ALL:ALL) NOPASSWD: ALL
```

# Quick install Xfce and required packages
```
git clone https://github.com/BeyonderLimit/debian-skeleton.git
cd debian-skeleton
sudo ./scripts/xfce-install.sh
```


