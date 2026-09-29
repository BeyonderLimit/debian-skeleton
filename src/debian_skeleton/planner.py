"""The plan stage: resolve a Selection into an immutable change plan.

Profiles produce requirements (catalogs); the planner resolves them against
live installed state and the configured APT repositories; nothing here
changes the machine.  The compatibility backstop re-checks the selection so
a bad one can never slip past the CLI into a plan value.
"""

from __future__ import annotations

from debian_skeleton.apt import query_installed
from debian_skeleton.apt import simulate as simulate_apt
from debian_skeleton.catalog.desktops import DESKTOP_PACKAGES, validate_selection
from debian_skeleton.catalog.packages import PURPOSE_PACKAGES, SIZE_PACKAGES
from debian_skeleton.models import Plan, Probe, Selection, Simulation
from debian_skeleton.runner import CommandRunner


class IncompatibleSelection(ValueError):
    """A selection the compatibility model rejects (the CLI maps this to exit 2)."""


def requirements_for(selection: Selection) -> tuple[str, ...]:
    """Union of every catalog set the selection implies, deduped and sorted."""
    wanted: set[str] = set(SIZE_PACKAGES[selection.size])
    wanted |= set(PURPOSE_PACKAGES[selection.purpose])
    wanted |= set(DESKTOP_PACKAGES[selection.desktop])
    if selection.window_manager == "openbox":
        wanted.add("openbox")  # the WM swap target rides along with the DE
    return tuple(sorted(wanted))


def plan_selection(
    selection: Selection,
    probe: Probe,
    runner: CommandRunner,
    *,
    simulate: bool = True,
) -> Plan:
    """Resolve a Selection against the machine; strictly read-only."""
    ok, explanation = validate_selection(selection)
    if not ok:
        raise IncompatibleSelection(explanation)

    warnings: list[str] = []
    if selection.purpose == "ai-assistant":
        warnings.append(
            "ai-assistant adds no packages by design: an LLM, voice stack, "
            "or model files are never installed silently"
        )
    if selection.desktop == "ukui":
        warnings.append(
            "ukui is experimental: Debian ships its components without a "
            "task or metapackage, so session completeness is not guaranteed"
        )

    requirements = requirements_for(selection)

    sessions = probe.installed.x_sessions + probe.installed.wayland_sessions
    if sessions and selection.desktop not in sessions:
        names = ", ".join(sessions)
        warnings.append(
            f"existing sessions are never removed automatically (installed: {names})"
        )

    if not requirements:
        missing: tuple[str, ...] = ()
    else:
        installed = query_installed(runner)
        if installed is None:
            warnings.append(
                "dpkg-query: installed state unknown; "
                "not filtering already-installed packages"
            )
            missing = requirements
        else:
            missing = tuple(p for p in requirements if p not in installed)

    simulation: Simulation | None = None
    if simulate:
        simulation = simulate_apt(runner, missing)
        if simulation is None:
            warnings.append(
                "apt-get --simulate: simulation unavailable; plan is unresolved"
            )
        elif simulation.unavailable:
            for package in simulation.unavailable:
                warnings.append(
                    f"apt: {package} is not available in the configured repositories"
                )
            drop = set(simulation.unavailable)
            missing = tuple(p for p in missing if p not in drop)
    elif missing:
        warnings.append(
            "apt checks skipped (--no-apt): the install set is unresolved "
            "catalog requirements, not checked against the repositories"
        )

    return Plan(
        selection=selection,
        packages_install=missing,
        packages_remove=(),  # never automatically remove an existing desktop
        config_changes=(),  # empty until the apply stage exists
        warnings=tuple(warnings),
        simulation=simulation,
    )
