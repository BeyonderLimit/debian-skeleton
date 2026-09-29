"""The probe stage: read-only inspection of the installed system."""

from __future__ import annotations

from debian_skeleton.models import Probe
from debian_skeleton.probe.context import ProbeContext, ProbeEnv
from debian_skeleton.probe.hardware import probe_hardware
from debian_skeleton.probe.installed import probe_installed
from debian_skeleton.probe.os import probe_os

__all__ = ["ProbeContext", "ProbeEnv", "run_probe"]


def run_probe(env: ProbeEnv | None = None) -> Probe:
    """Collect a full :class:`Probe` snapshot; strictly read-only."""
    env = env or ProbeEnv()
    ctx = ProbeContext(env)
    return Probe(
        root=str(env.root),
        os=probe_os(ctx),
        hardware=probe_hardware(ctx),
        installed=probe_installed(ctx),
        warnings=ctx.warnings,
    )
