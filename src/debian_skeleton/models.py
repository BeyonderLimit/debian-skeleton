"""Immutable data models.

The design rule from the README: profiles produce requirements; the planner
resolves them; only the apply layer changes the machine.  Every stage passes
frozen values, so a plan can be displayed, diffed, and confirmed.  Only the
probe models exist so far; ``Selection``/``Plan`` arrive with later
milestones.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class OsInfo:
    id: str | None  # "debian"
    version_id: str | None  # "12"
    version_codename: str | None  # "bookworm"
    pretty_name: str | None
    source_path: str | None  # which os-release file answered


@dataclass(frozen=True)
class MemoryInfo:
    # /proc/meminfo reports "kB", which is really KiB.
    total_kib: int | None
    available_kib: int | None  # older kernels omit MemAvailable
    swap_total_kib: int | None


@dataclass(frozen=True)
class DiskInfo:
    mount: str  # only the root filesystem for now
    block_size: int | None
    total_bytes: int | None
    free_bytes: int | None  # f_bfree: includes space reserved for root
    available_bytes: int | None  # f_bavail: what thresholds should use


@dataclass(frozen=True)
class BlockDevice:
    name: str
    type: str  # "disk" | "part" | "lvm" | ...
    size_bytes: int | None
    mountpoint: str | None  # may be None; "[SWAP]" is a real value
    model: str | None
    children: tuple["BlockDevice", ...] = ()


@dataclass(frozen=True)
class HardwareInfo:
    architecture: str | None  # dpkg architecture, e.g. "amd64"
    memory: MemoryInfo
    root_fs: DiskInfo
    block_devices: tuple[BlockDevice, ...]
    is_laptop: bool | None  # None = no hardware evidence either way
    laptop_evidence: tuple[str, ...]


@dataclass(frozen=True)
class InstalledInfo:
    x_sessions: tuple[str, ...]  # desktop-file stems, e.g. ("xfce",)
    wayland_sessions: tuple[str, ...]
    xorg_path: str | None

    @property
    def any_graphical_session(self) -> bool:
        return bool(self.x_sessions or self.wayland_sessions or self.xorg_path)


@dataclass(frozen=True)
class Probe:
    root: str  # what was probed: "/" or a fixture path
    os: OsInfo
    hardware: HardwareInfo
    installed: InstalledInfo
    warnings: tuple[str, ...]  # "source: message" strings


@dataclass(frozen=True)
class Selection:
    """The chosen configuration axes (from the user, or from a recommendation)."""

    size: str  # minimal | laptop | standard | full
    purpose: str  # daily | development | ai-assistant | custom
    desktop: str  # none | xfce | lxde | labwc | openbox | ukui
    window_manager: str | None  # only where the graphical stack permits


@dataclass(frozen=True)
class Recommendation:
    selection: Selection
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class Simulation:
    """What apt simulation says a plan would download and install."""

    newly_installed: tuple[str, ...]  # dependency closure from 'Inst' lines
    download_bytes: int | None
    disk_estimate_bytes: int | None
    unavailable: tuple[str, ...]  # not resolvable in the configured repos


@dataclass(frozen=True)
class Plan:
    """The immutable change plan the apply layer would one day execute."""

    selection: Selection
    packages_install: tuple[str, ...]
    packages_remove: tuple[str, ...] = ()  # always empty: never auto-remove a desktop
    config_changes: tuple[str, ...] = ()  # always empty until apply exists
    warnings: tuple[str, ...] = ()
    simulation: Simulation | None = None


@dataclass(frozen=True)
class ApplyStep:
    """One executable batch of an apply run (a single kind for now)."""

    kind: str  # "install" -- the only kind this milestone can execute
    packages: tuple[str, ...]
    executor: str  # "apt-get"; nala joins here later
    status: str  # pending | skipped | ok | partial | failed
    detail: str  # "" or why skipped / a failure excerpt


@dataclass(frozen=True)
class Manifest:
    """Durable record: what was intended (the Plan) and what happened."""

    schema_version: int  # 1; bump on incompatible shape change
    plan: Plan
    executor: str
    started_at: str  # ISO-8601 UTC; strings keep JSON trivial
    finished_at: str | None  # None while the run is still pending
    status: str  # pending | applied | noop | partial | failed
    steps: tuple[ApplyStep, ...]
    warnings: tuple[str, ...] = ()  # apply-time notes (drift skips etc.)


def probe_to_dict(probe: Probe) -> dict:
    """Convert a Probe into JSON-native types (nested tuples become lists)."""
    return asdict(probe)


def probe_to_json(probe: Probe, indent: int = 2) -> str:
    return json.dumps(probe_to_dict(probe), indent=indent) + "\n"


def recommendation_to_dict(recommendation: Recommendation) -> dict:
    return asdict(recommendation)


def recommendation_to_json(recommendation: Recommendation, indent: int = 2) -> str:
    return json.dumps(recommendation_to_dict(recommendation), indent=indent) + "\n"


def plan_to_dict(plan: Plan) -> dict:
    return asdict(plan)


def plan_to_json(plan: Plan, indent: int = 2) -> str:
    return json.dumps(plan_to_dict(plan), indent=indent) + "\n"


def manifest_to_dict(manifest: Manifest) -> dict:
    return asdict(manifest)


def manifest_to_json(manifest: Manifest, indent: int = 2) -> str:
    return json.dumps(manifest_to_dict(manifest), indent=indent) + "\n"


# -- strict re-reading of JSON documents ------------------------------------
#
# A plan file is about to change a machine, so reading is strict: unknown
# keys, wrong types, and anything this milestone cannot execute (removals,
# config changes) are rejected loudly instead of silently ignored.  Shape
# validation lives here; *policy* validation (axis membership, WM
# compatibility) is re-run by the apply layer -- models must not import the
# catalog (the catalog imports models.Selection; it would be a cycle).


class PlanFormatError(ValueError):
    """A plan/manifest JSON document that cannot be trusted to execute."""


STEP_STATUSES = frozenset({"pending", "skipped", "ok", "partial", "failed"})
MANIFEST_STATUSES = frozenset({"pending", "applied", "noop", "partial", "failed"})


def _object(data: object, where: str) -> dict:
    if not isinstance(data, dict):
        raise PlanFormatError(f"{where}: expected an object, got {type(data).__name__}")
    return data


def _only_known_keys(data: dict, allowed: set[str], where: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise PlanFormatError(f"{where}: unknown key {sorted(unknown)[0]!r}")


def _str_list(data: object, where: str) -> tuple[str, ...]:
    # asdict() keeps tuples while json.loads() produces lists -- accept both;
    # the strictness that matters is "only strings", not the container type.
    if not isinstance(data, (list, tuple)) or not all(isinstance(x, str) for x in data):
        raise PlanFormatError(f"{where}: expected a list of strings")
    return tuple(data)


def _str_or_none(data: object, where: str) -> str | None:
    if data is not None and not isinstance(data, str):
        raise PlanFormatError(f"{where}: expected a string or null")
    return data


def selection_from_dict(data: object) -> Selection:
    data = _object(data, "selection")
    _only_known_keys(data, {"size", "purpose", "desktop", "window_manager"}, "selection")
    for key in ("size", "purpose", "desktop", "window_manager"):
        if key not in data:
            raise PlanFormatError(f"selection: missing key {key!r}")
    for key in ("size", "purpose", "desktop"):
        if not isinstance(data[key], str):
            raise PlanFormatError(f"selection: {key} must be a string")
    return Selection(
        size=data["size"],
        purpose=data["purpose"],
        desktop=data["desktop"],
        window_manager=_str_or_none(data["window_manager"], "selection: window_manager"),
    )


def simulation_from_dict(data: object) -> Simulation:
    data = _object(data, "simulation")
    _only_known_keys(
        data,
        {"newly_installed", "download_bytes", "disk_estimate_bytes", "unavailable"},
        "simulation",
    )
    for key in ("newly_installed", "download_bytes", "disk_estimate_bytes", "unavailable"):
        if key not in data:
            raise PlanFormatError(f"simulation: missing key {key!r}")
    for key in ("download_bytes", "disk_estimate_bytes"):
        value = data[key]
        if value is not None and not isinstance(value, int):
            raise PlanFormatError(f"simulation: {key} must be an integer or null")
    return Simulation(
        newly_installed=_str_list(data["newly_installed"], "simulation: newly_installed"),
        download_bytes=data["download_bytes"],
        disk_estimate_bytes=data["disk_estimate_bytes"],
        unavailable=_str_list(data["unavailable"], "simulation: unavailable"),
    )


def plan_from_dict(data: object) -> Plan:
    data = _object(data, "plan")
    _only_known_keys(
        data,
        {"selection", "packages_install", "packages_remove",
         "config_changes", "warnings", "simulation"},
        "plan",
    )
    if "selection" not in data:
        raise PlanFormatError("plan: missing key 'selection'")
    if "packages_install" not in data:
        raise PlanFormatError("plan: missing key 'packages_install'")
    for key in ("packages_remove", "config_changes"):
        # Absent means empty; present-and-non-empty means the document asks
        # this tool to do something it cannot do -- refuse loudly.
        present = data.get(key, [])
        if present:
            raise PlanFormatError(
                f"plan: {key} is not empty; this tool never removes packages "
                "or edits configuration automatically"
            )
    simulation = data.get("simulation")
    return Plan(
        selection=selection_from_dict(data["selection"]),
        packages_install=_str_list(data["packages_install"], "plan: packages_install"),
        packages_remove=(),
        config_changes=(),
        warnings=_str_list(data.get("warnings", []), "plan: warnings"),
        simulation=None if simulation is None else simulation_from_dict(simulation),
    )


def apply_step_from_dict(data: object) -> ApplyStep:
    data = _object(data, "step")
    _only_known_keys(data, {"kind", "packages", "executor", "status", "detail"}, "step")
    for key in ("kind", "packages", "executor", "status", "detail"):
        if key not in data:
            raise PlanFormatError(f"step: missing key {key!r}")
    if data["status"] not in STEP_STATUSES:
        raise PlanFormatError(f"step: unknown status {data['status']!r}")
    for key in ("kind", "executor", "detail"):
        if not isinstance(data[key], str):
            raise PlanFormatError(f"step: {key} must be a string")
    return ApplyStep(
        kind=data["kind"],
        packages=_str_list(data["packages"], "step: packages"),
        executor=data["executor"],
        status=data["status"],
        detail=data["detail"],
    )


def manifest_from_dict(data: object) -> Manifest:
    data = _object(data, "manifest")
    _only_known_keys(
        data,
        {"schema_version", "plan", "executor", "started_at", "finished_at",
         "status", "steps", "warnings"},
        "manifest",
    )
    for key in ("schema_version", "plan", "executor", "started_at", "status", "steps"):
        if key not in data:
            raise PlanFormatError(f"manifest: missing key {key!r}")
    if data["schema_version"] != 1:
        raise PlanFormatError(
            f"manifest: unsupported schema_version {data['schema_version']!r} (expected 1)"
        )
    if data["status"] not in MANIFEST_STATUSES:
        raise PlanFormatError(f"manifest: unknown status {data['status']!r}")
    for key in ("executor", "started_at"):
        if not isinstance(data[key], str):
            raise PlanFormatError(f"manifest: {key} must be a string")
    if not isinstance(data["steps"], (list, tuple)):
        raise PlanFormatError("manifest: steps must be a list")
    return Manifest(
        schema_version=data["schema_version"],
        plan=plan_from_dict(data["plan"]),
        executor=data["executor"],
        started_at=data["started_at"],
        finished_at=_str_or_none(data["finished_at"], "manifest: finished_at"),
        status=data["status"],
        steps=tuple(apply_step_from_dict(step) for step in data["steps"]),
        warnings=_str_list(data.get("warnings", []), "manifest: warnings"),
    )
