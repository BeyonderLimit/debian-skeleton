"""TTY-friendly human rendering: pure functions, ASCII only, no rich."""

from __future__ import annotations

from debian_skeleton.models import BlockDevice, Manifest, Plan, Probe, Recommendation
from debian_skeleton.verify import VerifyReport


def format_bytes(count: int | None) -> str:
    if count is None:
        return "unknown"
    if count == 0:
        return "0 B"
    gib = count / 1024**3
    if gib >= 1:
        return f"{gib:.1f} GiB"
    mib = count / 1024**2
    if mib >= 1:
        return f"{mib:.1f} MiB"
    return f"{count / 1024:.1f} KiB"


def format_kib(kib: int | None) -> str:
    return format_bytes(kib * 1024 if kib is not None else None)


def _kv(label: str, value: object) -> str:
    return f"  {label:<18}{value}"


def _join_or_none(items: tuple[str, ...]) -> str:
    return ", ".join(items) if items else "none"


def _render_device(device: BlockDevice, indent: str) -> list[str]:
    line = f"{indent}{device.name}  {device.type}  {format_bytes(device.size_bytes)}"
    if device.mountpoint:
        line += f"  mounted at {device.mountpoint}"
    if device.model:
        line += f"  ({device.model})"
    lines = [line]
    for child in device.children:
        lines.extend(_render_device(child, indent + "  "))
    return lines


def render_probe(probe: Probe) -> str:
    lines: list[str] = []
    add = lines.append

    add("OS")
    add(_kv("distribution", probe.os.id or "unknown"))
    add(_kv("version", probe.os.version_id or "unknown"))
    add(_kv("codename", probe.os.version_codename or "unknown"))
    add(_kv("pretty name", probe.os.pretty_name or "unknown"))
    add(_kv("source", probe.os.source_path or "none"))
    add("")

    add("Hardware")
    add(_kv("architecture", probe.hardware.architecture or "unknown"))
    memory = probe.hardware.memory
    add(_kv("memory total", format_kib(memory.total_kib)))
    add(_kv("memory available", format_kib(memory.available_kib)))
    add(_kv("swap total", format_kib(memory.swap_total_kib)))
    root_fs = probe.hardware.root_fs
    add(_kv("root filesystem",
            f"total {format_bytes(root_fs.total_bytes)}, "
            f"available {format_bytes(root_fs.available_bytes)}"))
    add("")

    add("Block devices")
    if probe.hardware.block_devices:
        for device in probe.hardware.block_devices:
            lines.extend(_render_device(device, "  "))
    else:
        add("  none")
    add("")

    add("Sessions")
    add(_kv("X11", _join_or_none(probe.installed.x_sessions)))
    add(_kv("Wayland", _join_or_none(probe.installed.wayland_sessions)))
    add(_kv("X server", probe.installed.xorg_path or "none"))
    add("")

    add("Laptop classification")
    verdict = {True: "yes", False: "no"}.get(probe.hardware.is_laptop, "unknown")
    add(_kv("is laptop", verdict))
    if probe.hardware.laptop_evidence:
        for item in probe.hardware.laptop_evidence:
            add(_kv("evidence", item))
    else:
        add(_kv("evidence", "none"))
    add("")

    add("Warnings")
    if probe.warnings:
        for warning in probe.warnings:
            add(f"  - {warning}")
    else:
        add("  none")
    add("")

    return "\n".join(lines)


def render_recommendation(recommendation: Recommendation) -> str:
    selection = recommendation.selection
    lines = [
        "Recommendation",
        _kv("size", selection.size),
        _kv("purpose", selection.purpose),
        _kv("desktop", selection.desktop),
        _kv("window manager", selection.window_manager or "automatic"),
        "",
        "Reasons",
    ]
    if recommendation.reasons:
        lines.extend(f"  - {reason}" for reason in recommendation.reasons)
    else:
        lines.append("  none")
    lines.append("")
    return "\n".join(lines)


def render_plan(plan: Plan) -> str:
    selection = plan.selection
    lines: list[str] = []
    add = lines.append

    add("Plan")
    add(_kv("size", selection.size))
    add(_kv("purpose", selection.purpose))
    add(_kv("desktop", selection.desktop))
    add(_kv("window manager", selection.window_manager or "automatic"))
    add("")

    add("Install")
    if plan.packages_install:
        lines.extend(f"  - {package}" for package in plan.packages_install)
    else:
        add("  none")
    add("")

    if plan.simulation is not None:
        add("Simulation")
        add(_kv(
            "new packages",
            f"{len(plan.simulation.newly_installed)} (incl. dependencies)",
        ))
        add(_kv("download", format_bytes(plan.simulation.download_bytes)))
        add(_kv("disk estimate", format_bytes(plan.simulation.disk_estimate_bytes)))
        if plan.simulation.unavailable:
            add(_kv("unavailable", ", ".join(plan.simulation.unavailable)))
        add("")

    add("Remove")
    add("  none -- this plan removes nothing")
    add("")

    add("Config & services")
    add("  none -- no configuration files or services are touched")
    add("")

    add("Warnings")
    if plan.warnings:
        lines.extend(f"  - {warning}" for warning in plan.warnings)
    else:
        add("  none")
    add("")

    add("Plan only -- nothing will be changed.")
    add("")
    return "\n".join(lines)


def render_apply_result(manifest: Manifest, path: str) -> str:
    lines: list[str] = []
    add = lines.append

    add("Applied")
    add(_kv("manifest", path))
    add(_kv("executor", manifest.executor))
    add(_kv("status", manifest.status))
    add(_kv("started", manifest.started_at))
    if manifest.finished_at:
        add(_kv("finished", manifest.finished_at))
    add("")

    add("Steps")
    if manifest.steps:
        for step in manifest.steps:
            line = f"  - {step.kind}: {step.status} ({', '.join(step.packages) or 'no packages'})"
            add(line)
            if step.detail:
                for detail_line in step.detail.splitlines()[-4:]:
                    add(f"      {detail_line}")
    else:
        add("  none")
    add("")

    add("Warnings")
    if manifest.warnings:
        lines.extend(f"  - {warning}" for warning in manifest.warnings)
    else:
        add("  none")
    add("")
    return "\n".join(lines)


def render_verify(report: VerifyReport) -> str:
    lines: list[str] = []
    add = lines.append

    add("Verify")
    add(_kv("manifest", report.manifest_path))
    add(_kv("size", report.selection.size))
    add(_kv("purpose", report.selection.purpose))
    add(_kv("desktop", report.selection.desktop))
    add(_kv("window manager", report.selection.window_manager or "automatic"))
    add(_kv("status", report.status))
    add("")

    add("Steps")
    if report.steps:
        for step in report.steps:
            total = len(step.packages)
            line = (
                f"  - {step.kind}: {step.status} "
                f"({len(step.satisfied)}/{total} present)"
            )
            add(line)
            if step.missing:
                add(_kv("missing", ", ".join(step.missing)))
    else:
        add("  none -- this manifest records no steps")
    add("")
    return "\n".join(lines)
