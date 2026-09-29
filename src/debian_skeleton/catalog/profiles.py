"""Size/purpose definitions and the configurable heuristics for `recommend`.

Thresholds are heuristics, not requirements — they nudge a suggestion and
never block a user choice (README: "configurable heuristics—not hard
requirements or promises about performance").  Every threshold lives here so
tuning never touches decision logic.
"""

from __future__ import annotations

from dataclasses import dataclass

SIZES: tuple[str, ...] = ("minimal", "laptop", "standard", "full")
PURPOSES: tuple[str, ...] = ("daily", "development", "ai-assistant", "custom")
DESKTOPS: tuple[str, ...] = ("none", "xfce", "lxde", "labwc", "openbox", "ukui")


@dataclass(frozen=True)
class Heuristics:
    """RAM/disk thresholds (MiB) behind ``debian-skeleton recommend``."""

    # size tier upper bounds, ascending; above the last -> "full"
    minimal_ram_mib_max: int = 2048
    laptop_ram_mib_max: int = 4096
    standard_ram_mib_max: int = 16384
    # graphical stack when no session is installed yet
    no_desktop_ram_mib_max: int = 2048  # at or below -> keep it headless
    light_desktop_ram_mib_max: int = 4096  # at or below -> light desktop
    light_desktop: str = "lxde"
    default_desktop: str = "xfce"
    # available-space floor worth flagging on any profile
    disk_floor_mib: int = 4096
