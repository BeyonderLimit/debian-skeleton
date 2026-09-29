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


## Separate the choices

Right now, “build” means two different things. Make those independent axes:

| Choice | Values | What it controls |
|---|---|---|
| System size | Minimal, laptop, standard, full | How much desktop and general-purpose software to install |
| Intended use | Daily use, development, AI assistant, custom | Which additional tools and services to include |
| Graphical stack | None, Xfce, LXDE, labwc, Openbox, UKUI | The session or desktop experience |
| Window manager | Compatible option, or automatic | Only selectable where the graphical stack permits it |

I would treat **“Build” as the name of the planning operation**, not as a fifth size profile. For example, a user could choose `standard + development + Xfce` or `minimal + AI assistant + no desktop`.

The graphical choices need a compatibility model, not two unrestricted menus. Xfce and LXDE are desktop environments; Openbox is an X11 window manager; labwc is a Wayland compositor. A standalone window manager also needs choices for components such as a panel and session startup. Debian provides desktop task packages for Xfce and LXDE, while labwc is packaged separately. [packages.debian](https://packages.debian.org/trixie/task-lxde-desktop)

As implemented, a window-manager override (`openbox`) is accepted only for Xfce and LXDE: labwc and Openbox are complete sessions themselves, `none` is headless, and UKUI keeps its own window manager. Incompatible combinations are rejected with an explanation.

## The flow

1. **Probe:** Read `/etc/os-release`, `dpkg --print-architecture`, `/proc/meminfo`, root-filesystem free space, relevant block devices, and whether a graphical session is installed. Detect whether it is a laptop only when hardware evidence supports that classification. Every warning is data (“source: message”), never a crash.
2. **Recommend:** Suggest a size profile, use profile, and graphical stack. Treat RAM and disk thresholds as configurable heuristics—not hard requirements or promises about performance.
3. **Select:** Folded into `plan`: every axis can be overridden on the command line, and any axis you omit defaults to the recommendation (shown as provenance in the output). Incompatible desktop/window-manager combinations are filtered with an explanation.
4. **Plan:** Resolve package names against the configured APT repositories, check what is already installed, and display downloads, disk impact, removals, services, and configuration-file changes. APT supports simulation without changing the system. [people.debian](https://people.debian.org/~jak/apt-doc/man/apt-get.8.html)
5. **Apply:** Require root and a typed confirmation, record a manifest, then run narrowly scoped installation steps. Packages only — never an automatic desktop removal, never a config or service change.
6. **Verify:** Re-check a recorded manifest against the machine and report incomplete steps; repeat runs are safe. A manifest is a historical record and is never rewritten.

The first four steps are **read-only, and enforced as such** — planning runs only read-only commands (`dpkg-query`, `apt-cache`, `apt-get --simulate`, `apt-get --print-uris`). That makes the tool useful over SSH or from a TTY before you trust it to modify a machine.

Two APT behaviors verified live on Debian 12 (apt 2.6) shape the plan stage:

- `apt-get --simulate` aborts with no results if *any* requested package is unknown, so availability is settled first with `apt-cache policy` and only resolvable names are simulated; unavailable packages drop out of the plan with a warning (labwc on bookworm is the canonical case — it is trixie+ only).
- This apt version prints no download/disk summary under `--simulate`, so download bytes come from `--print-uris` and the disk estimate from `Installed-Size` stanzas.

## Usage

```bash
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'   # setup (pytest + rich are dev extras)

debian-skeleton probe                # inspect the system (read-only)
debian-skeleton probe --json         # machine-readable
debian-skeleton recommend            # suggested Selection + reasons
debian-skeleton plan                 # plan for the recommendation
debian-skeleton plan --size standard --desktop xfce
debian-skeleton plan --size minimal --purpose ai-assistant --desktop openbox
debian-skeleton plan --no-apt        # resolve without touching APT (unresolved warnings)
debian-skeleton probe --root PATH    # probe a different filesystem tree (commands disabled)

debian-skeleton plan --json > plan.json    # save the plan you reviewed
debian-skeleton apply plan.json --dry-run  # what would happen right now (read-only, no root)
sudo debian-skeleton apply plan.json       # install (asks you to type 'apply')
sudo debian-skeleton apply plan.json --yes # scripted apply of an explicit plan file
debian-skeleton verify                    # check the latest manifest (read-only)
debian-skeleton wizard                    # interactive Rich TUI: probe -> ... -> apply or save
```

`apply` is live-only by design (no `--root`: dpkg/apt cannot target a foreign tree). The wizard needs Rich — without it the core subcommands still work and `wizard` prints install guidance (`pip install '.[tui]'` or `apt install python3-rich`; Debian 12 ships python3-rich 13.3.1).

Exit codes are a contract:

| code | meaning |
|---|---|
| 0 | success — applied, nothing to do (noop), or verify satisfied |
| 1 | unexpected error |
| 2 | invalid input — bad selection, malformed plan file, no manifest found |
| 3 | refused before any change — not root, declined or impossible confirmation, plan drifted since it was saved |
| 4 | not converged — an apply step failed or ended partial, or verify found missing packages |

The typed phrase (`apply`, exact and case-sensitive) is only asked on a TTY; a piped run without `--yes` refuses rather than risk a stray line confirming an install. Apply is idempotent: packages already installed are skipped (a re-run records a `noop` manifest), while a plan whose packages disappeared from the repositories is refused with *re-run `plan`* — a confirmed plan is a value, and apply never re-plans behind your back. Every run writes a manifest first as `pending` and rewrites it with final per-step results, under `/var/lib/debian-skeleton/manifests/<UTC-timestamp>-<n>.json` (override with `--state-dir`); a crash leaves the intent on disk for forensics.

Example — the minimal AI-assistant combination stays honest about what it will and will not do:

```text
$ debian-skeleton plan --size minimal --purpose ai-assistant --desktop openbox

Plan
  size              minimal
  purpose           ai-assistant
  desktop           openbox
  window manager    automatic

Install
  - lxpanel
  - openbox
  - xterm

Simulation
  new packages      18 (incl. dependencies)
  download          3.5 MiB
  disk estimate     12.9 MiB

Remove
  none -- this plan removes nothing

Config & services
  none -- no configuration files or services are touched

Warnings
  - ai-assistant adds no packages by design: an LLM, voice stack, or model files are never installed silently
  - existing sessions are never removed automatically (installed: xfce)

Plan only -- nothing will be changed.
```
