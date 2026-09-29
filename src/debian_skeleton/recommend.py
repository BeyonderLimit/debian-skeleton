"""The recommend stage: turn a Probe into a suggested Selection, with reasons.

Pure decision logic over immutable values — no I/O.  Hardware evidence picks
a size and a graphical stack; without evidence the safest suggestion wins
and the gap is stated as a reason.
"""

from __future__ import annotations

from debian_skeleton.catalog.profiles import Heuristics
from debian_skeleton.models import Probe, Recommendation, Selection
from debian_skeleton.report import format_bytes

# Installed session stem -> desktop id from the DESKTOPS catalog axis.
_SESSION_TO_DESKTOP = {
    "xfce": "xfce",
    "lxde": "lxde",
    "labwc": "labwc",
    "openbox": "openbox",
    "ukui": "ukui",
}


def _ram_mib(probe: Probe) -> int | None:
    total_kib = probe.hardware.memory.total_kib
    return total_kib // 1024 if total_kib is not None else None


def _recommend_size(probe: Probe, h: Heuristics, reasons: list[str]) -> str:
    ram = _ram_mib(probe)
    if ram is None:
        reasons.append("no memory evidence; suggesting the smallest size profile")
        return "minimal"
    if ram <= h.minimal_ram_mib_max:
        reasons.append(f"RAM {ram} MiB fits the minimal profile")
        return "minimal"
    if ram <= h.laptop_ram_mib_max:
        reasons.append(f"RAM {ram} MiB fits the laptop profile")
        return "laptop"
    if ram <= h.standard_ram_mib_max:
        reasons.append(f"RAM {ram} MiB fits the standard profile")
        return "standard"
    reasons.append(f"RAM {ram} MiB supports the full profile")
    return "full"


def _recommend_desktop(probe: Probe, h: Heuristics, reasons: list[str]) -> str:
    sessions = probe.installed.x_sessions + probe.installed.wayland_sessions
    known = tuple(s for s in sessions if s in _SESSION_TO_DESKTOP)
    if known:
        reasons.append("graphical session already installed: " + ", ".join(sessions))
        return _SESSION_TO_DESKTOP[known[0]]
    if sessions:
        reasons.append(
            "installed session(s) "
            + ", ".join(sessions)
            + " not in the catalog; falling back to RAM-based suggestion"
        )
    ram = _ram_mib(probe)
    if ram is None:
        reasons.append("no memory evidence; suggesting no graphical stack")
        return "none"
    if ram <= h.no_desktop_ram_mib_max:
        reasons.append(f"RAM {ram} MiB is tight; suggesting no graphical stack")
        return "none"
    if ram <= h.light_desktop_ram_mib_max:
        reasons.append(
            f"RAM {ram} MiB suits a light desktop ({h.light_desktop})"
        )
        return h.light_desktop
    reasons.append(f"RAM {ram} MiB suits {h.default_desktop}")
    return h.default_desktop


def _note_disk(probe: Probe, h: Heuristics, reasons: list[str]) -> None:
    available = probe.hardware.root_fs.available_bytes
    if available is not None and available < h.disk_floor_mib * 1024 * 1024:
        reasons.append(
            f"only {format_bytes(available)} available on / — prefer a small profile"
        )


def recommend(probe: Probe, heuristics: Heuristics | None = None) -> Recommendation:
    """Suggest a Selection for this machine; every choice carries its reasons."""
    h = heuristics or Heuristics()
    reasons: list[str] = []
    size = _recommend_size(probe, h, reasons)
    desktop = _recommend_desktop(probe, h, reasons)
    _note_disk(probe, h, reasons)
    reasons.append("no evidence about intended use; defaulting to purpose 'daily'")
    return Recommendation(
        selection=Selection(size=size, purpose="daily", desktop=desktop, window_manager=None),
        reasons=tuple(reasons),
    )
