from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from debian_skeleton.models import Plan, Selection, Simulation
from debian_skeleton.planner import IncompatibleSelection, plan_selection
from debian_skeleton.probe import run_probe

# The laptop-bookworm simulate/uris/show payloads answer for the union of
# every selection tested on that machine, so both milestone combos that use
# it see this same canned closure and these totals.
UNION_CLOSURE = (
    "lxpanel", "openbox", "rsync", "task-xfce-desktop",
    "xdg-user-dirs", "xdg-utils", "xterm",
)
UNION_DOWNLOAD = 1475956
UNION_DISK = 9211904  # 8996 KiB of Installed-Size across the canned closure


@pytest.fixture
def laptop(make_env):
    env, _root = make_env("laptop-bookworm")
    return run_probe(env), env.runner


@pytest.fixture
def trixie(make_env):
    env, _root = make_env("desktop-trixie")
    return run_probe(env), env.runner


# -- the three milestone combinations -----------------------------------------


def test_standard_xfce_resolves_against_scripted_apt(laptop):
    probe, runner = laptop
    selection = Selection("standard", "daily", "xfce", None)
    assert plan_selection(selection, probe, runner) == Plan(
        selection=selection,
        packages_install=("rsync", "task-xfce-desktop", "xdg-utils"),
        simulation=Simulation(UNION_CLOSURE, UNION_DOWNLOAD, UNION_DISK, ()),
    )


def test_minimal_ai_assistant_openbox_warns_instead_of_installing(laptop):
    probe, runner = laptop
    plan = plan_selection(
        Selection("minimal", "ai-assistant", "openbox", None), probe, runner
    )
    assert plan.packages_install == ("lxpanel", "openbox", "xterm")
    assert plan.simulation == Simulation(UNION_CLOSURE, UNION_DOWNLOAD, UNION_DISK, ())
    # exactly the ai-assistant note and the existing-sessions guard
    assert plan.warnings[0].startswith("ai-assistant adds no packages")
    assert "never removed automatically" in plan.warnings[1]
    assert len(plan.warnings) == 2


def test_minimal_none_never_touches_apt(make_env):
    env, _root = make_env("server-minimal")
    probe = run_probe(env)
    plan = plan_selection(
        Selection("minimal", "daily", "none", None), probe, env.runner
    )
    assert plan.packages_install == ()
    assert plan.simulation == Simulation((), 0, 0, ())
    assert plan.warnings == ()


# -- availability, degradation, and guards -----------------------------------------


def test_unavailable_package_is_dropped_with_a_warning(laptop):
    # labwc is not in the bookworm repositories this fixture scripts
    probe, runner = laptop
    plan = plan_selection(Selection("minimal", "daily", "labwc", None), probe, runner)
    assert plan.packages_install == ()
    assert plan.simulation == Simulation((), None, None, ("labwc",))
    assert plan.warnings == (
        "apt: labwc is not available in the configured repositories",
    )


def test_labwc_resolves_on_trixie(trixie):
    probe, runner = trixie
    selection = Selection("standard", "daily", "labwc", None)
    assert plan_selection(selection, probe, runner) == Plan(
        selection=selection,
        packages_install=("labwc",),
        simulation=Simulation(("labwc",), 350000, 1536000, ()),
    )


def test_everything_installed_yields_empty_install(make_env):
    env, _root = make_env("server-minimal")
    probe = run_probe(env)
    plan = plan_selection(
        Selection("standard", "development", "none", None), probe, env.runner
    )
    assert plan.packages_install == ()
    assert plan.simulation == Simulation((), 0, 0, ())
    assert plan.warnings == ()


def test_degraded_machine_degrades_to_warnings_not_crashes(make_env):
    env, _root = make_env("degraded")
    probe = run_probe(env)
    plan = plan_selection(
        Selection("standard", "daily", "xfce", None), probe, env.runner
    )
    assert plan.simulation is None
    # unresolved: the full requirement list, unfiltered and unconfirmed
    assert plan.packages_install == (
        "bash-completion", "curl", "less",
        "rsync", "task-xfce-desktop", "xdg-utils",
    )
    assert plan.warnings == (
        "dpkg-query: installed state unknown; "
        "not filtering already-installed packages",
        "apt-get --simulate: simulation unavailable; plan is unresolved",
    )


def test_no_apt_skips_simulation_but_still_filters_installed(laptop):
    probe, runner = laptop
    plan = plan_selection(
        Selection("standard", "daily", "xfce", None), probe, runner, simulate=False
    )
    assert plan.simulation is None
    assert plan.packages_install == ("rsync", "task-xfce-desktop", "xdg-utils")
    assert plan.warnings == (
        "apt checks skipped (--no-apt): the install set is unresolved "
        "catalog requirements, not checked against the repositories",
    )


def test_switching_desktops_never_removes_the_existing_one(laptop):
    probe, runner = laptop
    plan = plan_selection(Selection("minimal", "daily", "lxde", None), probe, runner)
    assert plan.packages_remove == ()
    assert any("never removed automatically" in w for w in plan.warnings)


def test_incompatible_selection_raises_even_past_the_cli(laptop):
    probe, runner = laptop
    with pytest.raises(IncompatibleSelection):
        plan_selection(
            Selection("minimal", "daily", "labwc", "openbox"), probe, runner
        )


def test_ukui_selection_carries_the_experimental_note(laptop):
    probe, runner = laptop
    plan = plan_selection(Selection("minimal", "daily", "ukui", None), probe, runner)
    assert any("experimental" in w for w in plan.warnings)


def test_plan_is_frozen(laptop):
    probe, runner = laptop
    plan = plan_selection(
        Selection("minimal", "daily", "none", None), probe, runner
    )
    with pytest.raises(FrozenInstanceError):
        plan.packages_install = ("curl",)
