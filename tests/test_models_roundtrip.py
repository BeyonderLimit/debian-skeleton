from __future__ import annotations

import pytest

from debian_skeleton.models import (
    ApplyStep,
    Manifest,
    Plan,
    PlanFormatError,
    Selection,
    Simulation,
    manifest_from_dict,
    manifest_to_dict,
    plan_from_dict,
    plan_to_dict,
    selection_from_dict,
)

SELECTIONS = [
    Selection("minimal", "daily", "none", None),
    Selection("standard", "daily", "xfce", None),
    Selection("minimal", "ai-assistant", "openbox", None),
    Selection("standard", "development", "xfce", "openbox"),
]


# -- plans round-trip ---------------------------------------------------------


@pytest.mark.parametrize("selection", SELECTIONS)
def test_plan_round_trips_for_every_milestone_selection(selection):
    plan = Plan(
        selection=selection,
        packages_install=("rsync", "task-xfce-desktop"),
        simulation=Simulation(("rsync", "task-xfce-desktop"), 461728, 2213888, ()),
    )
    assert plan_from_dict(plan_to_dict(plan)) == plan


def test_plan_round_trips_without_simulation():
    plan = Plan(selection=Selection("minimal", "daily", "none", None),
                packages_install=())
    loaded = plan_from_dict(plan_to_dict(plan))
    assert loaded == plan
    assert loaded.simulation is None


def test_json_simulation_null_reads_back_as_none():
    document = plan_to_dict(Plan(selection=Selection("minimal", "daily", "none", None),
                                 packages_install=()))
    assert document["simulation"] is None
    assert plan_from_dict(document).simulation is None


# -- strict rejection -----------------------------------------------------------


def _base_plan_dict() -> dict:
    return plan_to_dict(
        Plan(selection=Selection("minimal", "daily", "none", None),
             packages_install=("curl",))
    )


def test_unknown_key_rejected():
    data = _base_plan_dict()
    data["packages"] = []
    with pytest.raises(PlanFormatError, match="unknown key 'packages'"):
        plan_from_dict(data)


def test_missing_selection_rejected():
    data = _base_plan_dict()
    del data["selection"]
    with pytest.raises(PlanFormatError, match="missing key 'selection'"):
        plan_from_dict(data)


def test_non_empty_packages_remove_rejected():
    data = _base_plan_dict()
    data["packages_remove"] = ["xfce4"]
    with pytest.raises(PlanFormatError, match="never removes"):
        plan_from_dict(data)


def test_non_empty_config_changes_rejected():
    data = _base_plan_dict()
    data["config_changes"] = ["/etc/lightdm/lightdm.conf"]
    with pytest.raises(PlanFormatError, match="never removes"):
        plan_from_dict(data)


def test_non_string_package_rejected():
    data = _base_plan_dict()
    data["packages_install"] = [42]
    with pytest.raises(PlanFormatError, match="list of strings"):
        plan_from_dict(data)


def test_non_null_window_manager_type_checked():
    data = _base_plan_dict()
    data["selection"]["window_manager"] = 7
    with pytest.raises(PlanFormatError, match="window_manager"):
        selection_from_dict(data["selection"])


def test_download_bytes_type_checked():
    data = _base_plan_dict()
    data["simulation"] = {
        "newly_installed": [], "download_bytes": "512",
        "disk_estimate_bytes": None, "unavailable": [],
    }
    with pytest.raises(PlanFormatError, match="download_bytes"):
        plan_from_dict(data)


# -- manifests round-trip ---------------------------------------------------------


def _manifest() -> Manifest:
    return Manifest(
        schema_version=1,
        plan=Plan(selection=Selection("minimal", "daily", "none", None),
                  packages_install=("curl",)),
        executor="apt-get",
        started_at="2026-09-28T10:15:00+00:00",
        finished_at="2026-09-28T10:15:42+00:00",
        status="applied",
        steps=(ApplyStep("install", ("curl",), "apt-get", "ok", ""),),
    )


def test_manifest_round_trips():
    manifest = _manifest()
    assert manifest_from_dict(manifest_to_dict(manifest)) == manifest


def test_pending_manifest_with_null_finished_at_reads_back():
    manifest = Manifest(
        schema_version=1,
        plan=_manifest().plan,
        executor="apt-get",
        started_at="2026-09-28T10:15:00+00:00",
        finished_at=None,
        status="pending",
        steps=(ApplyStep("install", ("curl",), "apt-get", "pending", ""),),
    )
    assert manifest_from_dict(manifest_to_dict(manifest)) == manifest


def test_manifest_bad_schema_version_rejected():
    data = manifest_to_dict(_manifest())
    data["schema_version"] = 2
    with pytest.raises(PlanFormatError, match="schema_version"):
        manifest_from_dict(data)


def test_manifest_bad_status_rejected():
    data = manifest_to_dict(_manifest())
    data["status"] = "exploded"
    with pytest.raises(PlanFormatError, match="unknown status"):
        manifest_from_dict(data)


def test_manifest_bad_step_status_rejected():
    data = manifest_to_dict(_manifest())
    data["steps"][0]["status"] = "mostly-fine"
    with pytest.raises(PlanFormatError, match="status"):
        manifest_from_dict(data)
