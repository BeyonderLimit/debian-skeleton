"""The verify stage: compare a recorded manifest against the live machine.

Verify is read-only and repeatable.  It re-queries dpkg once and classifies
every step against *current* state, so it catches both incomplete applies
and later drift.  A manifest is never rewritten here -- it is a historical
record, and what happened must not change when the machine does.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from debian_skeleton.apt import query_installed
from debian_skeleton.models import Manifest, Selection
from debian_skeleton.runner import CommandRunner


@dataclass(frozen=True)
class VerifyStep:
    kind: str
    packages: tuple[str, ...]
    satisfied: tuple[str, ...]
    missing: tuple[str, ...]
    status: str  # satisfied | partial | incomplete | unknown


@dataclass(frozen=True)
class VerifyReport:
    manifest_path: str
    selection: Selection
    status: str  # satisfied | partial | incomplete | unknown
    steps: tuple[VerifyStep, ...]


def find_latest_manifest(state_dir: Path) -> Path | None:
    """The newest manifest: filenames carry no status, so name order is time."""
    manifests = state_dir / "manifests"
    if not manifests.is_dir():
        return None
    files = sorted(manifests.glob("*.json"))
    return files[-1] if files else None


def _worst(statuses: list[str]) -> str:
    # A step skipped at apply time still gets checked now: packages may
    # have been removed since.  Everyone present -> satisfied; nobody ->
    # incomplete; some -> partial; unreadable state -> unknown.
    if "unknown" in statuses:
        return "unknown"
    if not statuses or all(s == "satisfied" for s in statuses):
        return "satisfied"
    if any(s == "satisfied" for s in statuses):
        return "partial"
    if any(s == "partial" for s in statuses):
        return "partial"
    return "incomplete"


def verify_manifest(
    manifest: Manifest, runner: CommandRunner, *, manifest_path: str
) -> VerifyReport:
    """Classify each recorded step against a fresh dpkg-query."""
    installed = query_installed(runner)
    steps: list[VerifyStep] = []
    for step in manifest.steps:
        if installed is None:
            steps.append(VerifyStep(
                step.kind, step.packages, (), (), "unknown"
            ))
            continue
        satisfied = tuple(p for p in step.packages if p in installed)
        missing = tuple(p for p in step.packages if p not in installed)
        if not missing:
            status = "satisfied"
        elif satisfied:
            status = "partial"
        else:
            status = "incomplete"
        steps.append(VerifyStep(step.kind, step.packages, satisfied, missing, status))
    return VerifyReport(
        manifest_path=manifest_path,
        selection=manifest.plan.selection,
        status=_worst([step.status for step in steps]),
        steps=tuple(steps),
    )


def report_to_dict(report: VerifyReport) -> dict:
    return asdict(report)


def report_to_json(report: VerifyReport, indent: int = 2) -> str:
    return json.dumps(report_to_dict(report), indent=indent) + "\n"
