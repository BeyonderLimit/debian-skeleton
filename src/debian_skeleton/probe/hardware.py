"""Hardware probe: architecture, memory, root filesystem, block devices,
and evidence-based laptop classification."""

from __future__ import annotations

import json
from typing import Any

from debian_skeleton.models import (
    BlockDevice,
    DiskInfo,
    HardwareInfo,
    MemoryInfo,
)
from debian_skeleton.probe.context import ProbeContext

DPKG_ARCH_ARGV: tuple[str, ...] = ("dpkg", "--print-architecture")
# --bytes avoids parsing human sizes like "953.9G"; children nest
# automatically (util-linux 2.38 rejects an explicit CHILDREN column).
LSBLK_ARGV: tuple[str, ...] = (
    "lsblk",
    "--json",
    "--bytes",
    "--output",
    "NAME,TYPE,SIZE,MOUNTPOINT,MODEL",
)

# DMI chassis types (SMBIOS spec) that indicate a portable or a fixed
# machine; everything else counts as "no evidence".
CHASSIS_PORTABLE: frozenset[int] = frozenset({8, 9, 10, 11, 14, 30, 31, 32})
CHASSIS_FIXED: frozenset[int] = frozenset({3, 4, 5, 6, 7, 13, 15, 16, 23, 24, 35})

_CHASSIS_NAMES = {
    1: "Other",
    2: "Unknown",
    3: "Desktop",
    4: "Low Profile Desktop",
    5: "Pizza Box",
    6: "Mini Tower",
    7: "Tower",
    8: "Portable",
    9: "Laptop",
    10: "Notebook",
    11: "Hand Held",
    13: "All In One",
    14: "Sub Notebook",
    15: "Space-saving",
    16: "Lunch Box",
    23: "Rack Mount Chassis",
    24: "Sealed Case PC",
    30: "Tablet",
    31: "Convertible",
    32: "Detachable",
    35: "Mini PC",
}


def parse_meminfo(text: str) -> dict[str, int]:
    """Parse /proc/meminfo lines into a ``{key: KiB}`` map."""
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, sep, rest = line.partition(":")
        if not sep:
            continue
        fields = rest.split()
        if not fields:
            continue
        try:
            values[key] = int(fields[0])
        except ValueError:
            continue
    return values


def parse_lsblk(text: str) -> tuple[BlockDevice, ...]:
    """Parse ``lsblk --json --bytes`` output into nested BlockDevice values."""

    def to_device(entry: dict[str, Any]) -> BlockDevice:
        return BlockDevice(
            name=entry.get("name", ""),
            type=entry.get("type", ""),
            size_bytes=entry.get("size"),
            mountpoint=entry.get("mountpoint"),
            model=entry.get("model"),
            children=tuple(to_device(child) for child in entry.get("children", ())),
        )

    payload = json.loads(text)
    return tuple(to_device(entry) for entry in payload.get("blockdevices", ()))


def classify_laptop(
    batteries: tuple[str, ...], chassis_type: int | None
) -> tuple[bool | None, tuple[str, ...]]:
    """Classify laptop-ness from hardware evidence only; ``None`` without any.

    A battery is the strongest evidence and wins even over a fixed chassis
    (vendor DMI data is unreliable); everything that contributed is recorded
    as an evidence string so the verdict stays auditable.
    """
    evidence: list[str] = []
    if batteries:
        evidence.append("battery present: " + ", ".join(batteries))
    chassis_name = (
        _CHASSIS_NAMES.get(chassis_type) if chassis_type is not None else None
    )
    if chassis_name is not None:
        evidence.append(f"DMI chassis type {chassis_type} ({chassis_name})")

    if batteries:
        return True, tuple(evidence)
    if chassis_type in CHASSIS_PORTABLE:
        return True, tuple(evidence)
    if chassis_type in CHASSIS_FIXED:
        return False, tuple(evidence)
    return None, tuple(evidence)


def _probe_architecture(ctx: ProbeContext) -> str | None:
    result = ctx.run(DPKG_ARCH_ARGV)
    if result is None:
        return None  # ctx.run already warned
    if result.returncode != 0:
        ctx.warn(
            "dpkg --print-architecture",
            f"exit {result.returncode}: {result.stderr.strip()}",
        )
        return None
    return result.stdout.strip() or None


def _probe_memory(ctx: ProbeContext) -> MemoryInfo:
    text = ctx.read_text("proc/meminfo")
    if text is None:
        return MemoryInfo(total_kib=None, available_kib=None, swap_total_kib=None)
    values = parse_meminfo(text)
    return MemoryInfo(
        total_kib=values.get("MemTotal"),
        available_kib=values.get("MemAvailable"),
        swap_total_kib=values.get("SwapTotal"),
    )


def _probe_root_fs(ctx: ProbeContext) -> DiskInfo:
    stats = ctx.statvfs_root()
    if stats is None:
        return DiskInfo(
            mount="/", block_size=None, total_bytes=None,
            free_bytes=None, available_bytes=None,
        )
    block = stats.f_bsize
    return DiskInfo(
        mount="/",
        block_size=block,
        total_bytes=stats.f_blocks * block,
        free_bytes=stats.f_bfree * block,
        available_bytes=stats.f_bavail * block,
    )


def _probe_block_devices(ctx: ProbeContext) -> tuple[BlockDevice, ...]:
    result = ctx.run(LSBLK_ARGV)
    if result is None:
        return ()  # ctx.run already warned
    if result.returncode != 0:
        ctx.warn(
            "lsblk", f"exit {result.returncode}: {result.stderr.strip()}"
        )
        return ()
    try:
        return parse_lsblk(result.stdout)
    except json.JSONDecodeError as exc:
        ctx.warn("lsblk", f"unparseable JSON output: {exc}")
        return ()


def _probe_laptop(ctx: ProbeContext) -> tuple[bool | None, tuple[str, ...]]:
    batteries: list[str] = []
    supplies = ctx.list_dir("sys/class/power_supply")
    if supplies is not None:
        for supply in supplies:
            type_text = ctx.read_optional_text(
                f"sys/class/power_supply/{supply.name}/type"
            )
            if type_text is not None and type_text.strip() == "Battery":
                batteries.append(supply.name)
    chassis_raw = ctx.read_optional_text("sys/class/dmi/id/chassis_type")
    chassis_type: int | None = None
    if chassis_raw is not None:
        try:
            chassis_type = int(chassis_raw.strip())
        except ValueError:
            ctx.warn(
                "sys/class/dmi/id/chassis_type",
                f"unparseable value {chassis_raw.strip()!r}",
            )
    return classify_laptop(tuple(batteries), chassis_type)


def probe_hardware(ctx: ProbeContext) -> HardwareInfo:
    is_laptop, laptop_evidence = _probe_laptop(ctx)
    return HardwareInfo(
        architecture=_probe_architecture(ctx),
        memory=_probe_memory(ctx),
        root_fs=_probe_root_fs(ctx),
        block_devices=_probe_block_devices(ctx),
        is_laptop=is_laptop,
        laptop_evidence=laptop_evidence,
    )
