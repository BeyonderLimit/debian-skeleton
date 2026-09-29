from __future__ import annotations

import pytest

from debian_skeleton.catalog.desktops import (
    DESKTOP_PACKAGES,
    WINDOW_MANAGERS,
    validate_selection,
)
from debian_skeleton.catalog.packages import PURPOSE_PACKAGES, SIZE_PACKAGES
from debian_skeleton.catalog.profiles import DESKTOPS, PURPOSES, SIZES
from debian_skeleton.models import Selection
from debian_skeleton.planner import requirements_for


def select(**overrides) -> Selection:
    base = {"size": "minimal", "purpose": "daily",
            "desktop": "none", "window_manager": None}
    return Selection(**{**base, **overrides})


# -- the three milestone combinations -----------------------------------------


def test_requirements_minimal_none_is_empty():
    assert requirements_for(select()) == ()


def test_requirements_standard_xfce_is_standard_set_plus_task():
    wanted = requirements_for(select(size="standard", desktop="xfce"))
    assert "task-xfce-desktop" in wanted
    assert set(SIZE_PACKAGES["standard"]) <= set(wanted)
    assert wanted == tuple(sorted(wanted))  # deduped, deterministic order


def test_requirements_minimal_ai_assistant_openbox_is_the_openbox_trio():
    # ai-assistant deliberately contributes nothing; only the session remains
    assert requirements_for(
        select(purpose="ai-assistant", desktop="openbox")
    ) == ("lxpanel", "openbox", "xterm")


def test_requirements_wm_override_rides_along_with_a_desktop():
    wanted = requirements_for(select(desktop="xfce", window_manager="openbox"))
    assert "task-xfce-desktop" in wanted
    assert "openbox" in wanted


# -- compatibility truth table ----------------------------------------------------


@pytest.mark.parametrize("desktop", ["xfce", "lxde"])
def test_window_manager_allowed_for_replaceable_desktops(desktop):
    ok, _explanation = validate_selection(
        select(desktop=desktop, window_manager="openbox")
    )
    assert ok


@pytest.mark.parametrize("desktop", ["none", "labwc", "openbox", "ukui"])
def test_window_manager_rejected_elsewhere(desktop):
    ok, explanation = validate_selection(
        select(desktop=desktop, window_manager="openbox")
    )
    assert not ok
    assert explanation != "ok"


def test_no_window_manager_is_always_compatible():
    for desktop in DESKTOPS:
        assert validate_selection(select(desktop=desktop))[0]


def test_unknown_window_manager_rejected():
    assert not validate_selection(select(window_manager="i3"))[0]


# -- catalogs stay in sync with the profile axes -----------------------------------


def test_catalog_keys_match_profile_axes():
    assert set(SIZE_PACKAGES) == set(SIZES)
    assert set(PURPOSE_PACKAGES) == set(PURPOSES)
    assert set(DESKTOP_PACKAGES) == set(DESKTOPS)
    assert WINDOW_MANAGERS  # at least one selectable WM exists
