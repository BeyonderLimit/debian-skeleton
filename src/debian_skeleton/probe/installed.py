"""Installed-software probe: graphical session evidence (for now)."""

from __future__ import annotations

from pathlib import Path

from debian_skeleton.models import InstalledInfo
from debian_skeleton.probe.context import ProbeContext

XORG_CANDIDATES: tuple[str, ...] = (
    "/usr/bin/Xorg",
    "/usr/lib/xorg/Xorg",
    "/usr/libexec/Xorg",
)


def _session_stems(ctx: ProbeContext, rel_dir: str) -> tuple[str, ...]:
    # A missing session directory is normal on a minimal install (this
    # machine has no /usr/share/wayland-sessions), so absence is no warning.
    entries = ctx.list_dir(rel_dir)
    if entries is None:
        return ()
    return tuple(entry.stem for entry in entries if entry.suffix == ".desktop")


def _first_existing(ctx: ProbeContext, absolute_candidates: tuple[str, ...]) -> str | None:
    for candidate in absolute_candidates:
        if ctx.exists(candidate.lstrip("/")):
            return candidate
    return None


def probe_installed(ctx: ProbeContext) -> InstalledInfo:
    return InstalledInfo(
        x_sessions=_session_stems(ctx, "usr/share/xsessions"),
        wayland_sessions=_session_stems(ctx, "usr/share/wayland-sessions"),
        xorg_path=_first_existing(ctx, XORG_CANDIDATES),
    )
