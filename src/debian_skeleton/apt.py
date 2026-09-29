"""Read-only APT/dpkg queries, all through the command runner seam.

Parsers are pure; collectors return ``None`` when a command could not run at
all (missing binary, timeout, skipped) and let the planner record the
warning.  Formats follow apt-get 2.6 / dpkg 1.21 on Debian 12, verified
live.  Two facts shape this module:

- ``apt-get --simulate`` ABORTS with no ``Inst`` lines as soon as one
  requested package is unknown (verified), so availability is settled first
  with ``apt-cache policy`` and only resolvable names reach the simulation.
- ``apt-get --simulate`` prints no download/disk summary on this version,
  so byte numbers come from ``--print-uris`` (download) and ``apt-cache
  show`` ``Installed-Size:`` (disk estimate).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from debian_skeleton.models import Simulation
from debian_skeleton.runner import CommandError, CommandResult, CommandRunner

APT_TIMEOUT = 60.0  # apt calls resolve far more than the probe's 10 s default

DPKG_QUERY_ARGV: tuple[str, ...] = (
    "dpkg-query",
    "-W",
    "-f=${binary:Package}\t${db:Status-Abbrev}\n",
)

_UNAVAILABLE = re.compile(
    r"Unable to locate package (\S+)|Package '(\S+)' has no installation candidate"
)


def apt_policy_argv(packages: Iterable[str]) -> tuple[str, ...]:
    return ("apt-cache", "policy", *packages)


def apt_simulate_argv(packages: Iterable[str]) -> tuple[str, ...]:
    return ("apt-get", "--simulate", "install", "--", *packages)


def apt_print_uris_argv(packages: Iterable[str]) -> tuple[str, ...]:
    return ("apt-get", "--print-uris", "--yes", "install", "--", *packages)


def apt_show_argv(packages: Iterable[str]) -> tuple[str, ...]:
    return ("apt-cache", "show", "--", *packages)


def apt_install_argv(packages: Iterable[str]) -> tuple[str, ...]:
    """The apply-time install command; flags must mirror what plan simulated.

    ``--yes`` is required: the runner captures stdio, so an unprompted
    "continue?" would read the operator's terminal mid-transaction.  The
    ``Dpkg::Options`` pair is the standard unattended conffile policy (keep
    the existing file when a package ships an updated one) and does not
    change the resolved closure.  Deliberately NO ``--no-install-recommends``:
    the plan stage simulates plain ``install``, so executing anything else
    would install something other than what was displayed and confirmed.
    """
    return (
        "apt-get", "--yes",
        "-o", "Dpkg::Options::=--force-confdef",
        "-o", "Dpkg::Options::=--force-confold",
        "install", "--", *packages,
    )


# -- pure parsers -------------------------------------------------------------


def parse_dpkg_query(text: str) -> frozenset[str]:
    """Installed names from dpkg-query -W; the 3-char status abbrev starts 'ii'."""
    installed: set[str] = set()
    for line in text.splitlines():
        name, sep, status = line.partition("\t")
        if sep and status.startswith("ii"):
            installed.add(name.strip())
    return frozenset(installed)


def parse_policy(stdout: str, stderr: str, packages: Iterable[str]) -> tuple[str, ...]:
    """Requested packages that have a real candidate in the configured repos.

    ``apt-cache policy`` prints one indented stanza per ``name:`` header; a
    package is available iff its stanza carries a ``Candidate:`` line other
    than ``(none)``.  Missing packages produce no stanza at all.
    """
    lines = (stdout + "\n" + stderr).splitlines()
    available: list[str] = []
    for package in packages:
        try:
            start = lines.index(f"{package}:")
        except ValueError:
            continue
        for line in lines[start + 1:]:
            if line and not line[0].isspace():
                break  # next stanza
            value = line.strip().partition("Candidate:")[2].strip()
            if line.strip().startswith("Candidate:") and value and value != "(none)":
                available.append(package)
                break
    return tuple(available)


def parse_simulate(text: str) -> tuple[str, ...]:
    """Sorted newly-installed closure from 'Inst pkg (...)' lines."""
    names = [
        fields[1]
        for line in text.splitlines()
        if (fields := line.split()) and fields[0] == "Inst"
    ]
    return tuple(sorted(names))


def parse_unavailable(text: str) -> tuple[str, ...]:
    """Package names from 'Unable to locate' / 'no installation candidate' lines."""
    found: list[str] = []
    for match in _UNAVAILABLE.finditer(text):
        name = match.group(1) or match.group(2)
        if name not in found:
            found.append(name)
    return tuple(found)


def parse_print_uris(text: str) -> int | None:
    """Sum the per-deb byte field; None when the output holds no debs."""
    total = 0
    seen = False
    for line in text.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[2].replace(",", "").isdigit():
            total += int(fields[2].replace(",", ""))  # tolerate locale commas
            seen = True
    return total if seen else None


def parse_apt_show(text: str) -> int | None:
    """Sum Installed-Size stanzas (KiB -> bytes); None when absent."""
    total_kib = 0
    seen = False
    for line in text.splitlines():
        if line.startswith("Installed-Size:"):
            value = line.partition(":")[2].strip().replace(",", "")
            try:
                total_kib += int(value)
            except ValueError:
                continue
            seen = True
    return total_kib * 1024 if seen else None


# -- collectors over the runner seam --------------------------------------------


def _run(runner: CommandRunner, argv: tuple[str, ...]) -> CommandResult | None:
    try:
        return runner.run(argv, timeout=APT_TIMEOUT)
    except CommandError:
        return None


def query_installed(runner: CommandRunner) -> frozenset[str] | None:
    """Names of installed packages; None when dpkg-query could not answer."""
    result = _run(runner, DPKG_QUERY_ARGV)
    if result is None or result.returncode != 0:
        return None
    return parse_dpkg_query(result.stdout)


def check_available(
    runner: CommandRunner, packages: tuple[str, ...]
) -> tuple[str, ...] | None:
    """Which of ``packages`` the configured repositories can provide."""
    if not packages:
        return ()
    result = _run(runner, apt_policy_argv(packages))
    if result is None:
        return None
    return parse_policy(result.stdout, result.stderr, packages)


def simulate(runner: CommandRunner, packages: tuple[str, ...]) -> Simulation | None:
    """One simulation pass over resolvable packages.

    Policy runs first (apt-get -s aborts on unknown names — verified), then
    resolution (-s), download size (--print-uris), and disk estimate
    (apt-cache show).  None only when a command could not run at all;
    partial failures degrade to None fields inside the Simulation.
    """
    if not packages:
        return Simulation(
            newly_installed=(), download_bytes=0, disk_estimate_bytes=0,
            unavailable=(),
        )
    available = check_available(runner, packages)
    if available is None:
        return None
    unavailable = tuple(p for p in packages if p not in available)
    if not available:
        return Simulation(
            newly_installed=(), download_bytes=None, disk_estimate_bytes=None,
            unavailable=unavailable,
        )

    result = _run(runner, apt_simulate_argv(available))
    if result is None:
        return None
    newly = parse_simulate(result.stdout)
    if result.returncode != 0:
        # Defensive: policy and -s disagreed; fold whatever -s reported.
        unavailable = tuple(sorted(
            set(unavailable)
            | set(parse_unavailable(result.stdout + "\n" + result.stderr))
        ))

    uris = _run(runner, apt_print_uris_argv(available))
    downloads = parse_print_uris(uris.stdout) if uris is not None else None
    show = _run(runner, apt_show_argv(newly or available))
    disk = parse_apt_show(show.stdout) if show is not None else None
    return Simulation(
        newly_installed=newly,
        download_bytes=downloads,
        disk_estimate_bytes=disk,
        unavailable=unavailable,
    )
