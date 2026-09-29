# Debian Skeleton

A **TTY-first, post-install Debian configurator**: inspect the installed system, recommend a profile, show an exact plan, and apply it only after confirmation. I would keep it separate from building Debian installation images; image creation can become another backend later.

**Status:** the first two milestones are complete and usable — `probe`, `recommend`, `plan`, `apply`, and `verify` are implemented as a stdlib-only Python CLI (no runtime dependencies; it must run on a fresh Debian install before APT repositories are trusted), plus an optional Rich TUI wizard (`pip install '.[tui]'` or `apt install python3-rich`).

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

## Project structure

```text
debian-skeleton/
├── pyproject.toml
├── README.md
├── src/debian_skeleton/
│   ├── cli.py              # probe, recommend, plan, apply, verify, wizard
│   ├── models.py           # Probe, Selection, Recommendation, Simulation, Plan, ApplyStep, Manifest
│   ├── runner.py           # CommandRunner seam: subprocess / offline runners
│   ├── probe/
│   │   ├── context.py      # ProbeEnv / ProbeContext: forgiving, injectable I/O
│   │   ├── os.py
│   │   ├── hardware.py
│   │   └── installed.py
│   ├── catalog/
│   │   ├── profiles.py     # Choice axes + configurable recommend heuristics
│   │   ├── desktops.py     # Session components + the compatibility model
│   │   └── packages.py     # Size and intended-use package sets (pure data)
│   ├── recommend.py        # Probe evidence -> Recommendation with reasons
│   ├── apt.py              # Read-only availability checks and simulation
│   ├── planner.py          # Selection -> immutable Plan
│   ├── report.py           # TTY-friendly output (stdlib/ASCII; works headless)
│   ├── apply.py            # Confirmed installs only; manifests, drift policy
│   ├── verify.py           # Manifest vs machine, read-only, never rewrites
│   └── wizard.py           # Optional Rich TUI (the only module importing rich)
└── tests/
    ├── fixtures/           # Fake machine trees + canned command outputs
    ├── test_probe_*.py     # probe stages, fixtures, e2e
    ├── test_recommend.py
    ├── test_apt.py         # parsers + collectors vs verified apt formats
    ├── test_catalog.py     # compatibility model + requirements
    ├── test_planner.py     # the milestone combinations, end to end
    ├── test_apply.py, test_verify.py, test_wizard.py, test_models_roundtrip.py
    ├── test_cli.py, test_report.py, test_runner.py, test_support.py
    └── conftest.py         # make_env / make_apply_env: scripted, rootless, fixed clock
```

Tests replay recorded machine evidence (filesystem trees plus scripted command outputs keyed by argv prefix), so no test needs a real Debian system — while the three milestone combinations are also verified live.

Use a small data model at the center:

```python
@dataclass(frozen=True)
class Selection:
    size: str                 # minimal | laptop | standard | full
    purpose: str              # daily | development | ai-assistant | custom
    desktop: str              # none | xfce | lxde | labwc | openbox | ukui
    window_manager: str | None

@dataclass(frozen=True)
class Simulation:             # what apt simulation says a plan would do
    newly_installed: tuple[str, ...]
    download_bytes: int | None
    disk_estimate_bytes: int | None
    unavailable: tuple[str, ...]

@dataclass(frozen=True)
class Plan:
    selection: Selection
    packages_install: tuple[str, ...]
    packages_remove: tuple[str, ...]   # always empty: never auto-remove a desktop
    config_changes: tuple[str, ...]    # always empty: apply is packages-only
    warnings: tuple[str, ...]
    simulation: Simulation | None = None

@dataclass(frozen=True)
class ApplyStep:                  # one executed step, as recorded
    kind: str                     # "install" (only kind, for now)
    packages: tuple[str, ...]
    executor: str                 # "apt-get"
    status: str                   # pending | skipped | ok | partial | failed
    detail: str                   # stderr tail when something failed

@dataclass(frozen=True)
class Manifest:                   # what apply did (or intended, if it crashed)
    schema_version: int           # 1
    plan: Plan                    # the exact confirmed value that ran
    executor: str
    started_at: str               # UTC ISO-8601
    finished_at: str | None       # null while the run is still pending
    status: str                   # pending | applied | noop | partial | failed
    steps: tuple[ApplyStep, ...]
    warnings: tuple[str, ...]
```

The key design rule is: **profiles produce requirements; the planner resolves them; only the apply layer changes the machine.** For your constrained-device AI-assistant use case, that means the profile can recommend a minimal or lightweight graphical setup without silently installing an LLM, voice stack, or model files — the ai-assistant profile deliberately contributes no packages and says so in a warning.

## Milestones

**First milestone — done.** `probe`, `recommend`, and `plan` as a Python CLI, with the three tested combinations `minimal + none`, `standard + Xfce`, and `minimal + AI assistant + Openbox` (137 tests; all three combinations also verified against live APT). The other desktop and window-manager options are catalogued but wait on compatibility checks and package-resolution tests before being trusted in plans. Debian’s own installation figures show why planning against actual available space matters: its Xfce and LXDE desktop tasks require substantially more space than a minimal base installation. [debian](https://www.debian.org/releases/trixie/amd64/apds02.en.html)

**Second milestone — done.** `apply`, `verify`, and the Rich wizard ("dressing the skeleton"): typed confirmation on a TTY, pending-then-final manifests under `/var/lib/debian-skeleton`, idempotent re-runs (`noop`), drift refusal, packages-only scope (a plan file carrying removals or config changes is rejected loudly), and a scripted-wizard test suite in which no real `apt-get install` ever runs (214 tests). The executor stays pluggable (apt-get as the substrate; nala as an optional faster installer at apply time), since planning gains nothing from either.

**Next: doctor.** A diagnostic subcommand: is the tool usable on this machine (root, network, APT state), and a reconciliation pass over historical manifests. Configuration changes beyond packages remain deliberately out of scope until apply has real-world mileage.
