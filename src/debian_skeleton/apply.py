"""The apply stage: execute a confirmed Plan, narrowly and on the record.

Everything here is built to be refused rather than guessed: apply demands
root, re-validates the plan's policy, and re-resolves it against the live
machine because state may have drifted since the plan was confirmed.
Already-installed packages are skipped (re-runs are safe); packages that
became unavailable refuse the whole run -- a plan is a confirmed value, and
substituting a different one is the planner's job, never apply's.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from debian_skeleton.apt import apt_install_argv, check_available, query_installed
from debian_skeleton.catalog.desktops import DESKTOP_PACKAGES, validate_selection
from debian_skeleton.catalog.packages import PURPOSE_PACKAGES, SIZE_PACKAGES
from debian_skeleton.models import ApplyStep, Manifest, Plan, manifest_to_json
from debian_skeleton.planner import IncompatibleSelection
from debian_skeleton.runner import CommandError, CommandRunner, SubprocessRunner

DEFAULT_STATE_DIR = Path("/var/lib/debian-skeleton")
# One apt transaction may legitimately take minutes; APT_TIMEOUT is a
# read-only budget and would kill dpkg mid-configuration on slow mirrors.
INSTALL_TIMEOUT = 1800.0

CONFIRM_PHRASE = "apply"


@dataclass(frozen=True)
class ApplyEnv:
    """The apply-stage injection bundle (mirrors ProbeEnv).

    ``euid``/``now`` are callables, not values, so CLI-level tests can
    monkeypatch ``os.geteuid`` and unit tests can fix the clock.  There is
    deliberately no ``root`` field: apt/dpkg cannot target a foreign tree,
    so apply only ever works on the live system.
    """

    state_dir: Path = DEFAULT_STATE_DIR
    runner: CommandRunner = field(default_factory=SubprocessRunner)
    euid: Callable[[], int] = lambda: os.geteuid()
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)


class ApplyError(RuntimeError):
    """Apply refused to run (root/state/availability problems)."""


class NotRootError(ApplyError):
    """apply requires euid 0; it never elevates itself."""


class PlanDriftError(ApplyError):
    """The confirmed plan no longer matches what the machine can do."""


@dataclass(frozen=True)
class Executor:
    """Named install-command builder: apt-get now, nala optionally later.

    The executor only shapes argv -- the runner stays the single execution
    seam, which is what keeps apply testable against scripted results.
    """

    name: str
    install_argv: Callable[[tuple[str, ...]], tuple[str, ...]]


APT_GET = Executor("apt-get", apt_install_argv)
NONINTERACTIVE_ENV = (("DEBIAN_FRONTEND", "noninteractive"),)


@dataclass(frozen=True)
class Resolution:
    """What apply would do with this plan on this machine, right now."""

    install: tuple[str, ...]  # missing AND available -> would install
    skip_installed: tuple[str, ...]  # already present -> idempotent skip
    unavailable: tuple[str, ...]  # was plannable, now is not -> refuse
    state_known: bool  # dpkg-query answered
    availability_known: bool  # apt-cache policy answered


def phrase_ok(answer: str, phrase: str = CONFIRM_PHRASE) -> bool:
    """Exact, case-sensitive match; 'APPLY' and 'apply ' must not pass."""
    return answer == phrase


def require_executable(plan: Plan) -> None:
    """Re-run the policy checks; a saved plan is still subject to them."""
    _ok, explanation = validate_selection(plan.selection)
    if not _ok:
        raise IncompatibleSelection(explanation)
    selection = plan.selection
    if (
        selection.size not in SIZE_PACKAGES
        or selection.purpose not in PURPOSE_PACKAGES
        or selection.desktop not in DESKTOP_PACKAGES
    ):
        raise IncompatibleSelection(
            f"unknown axis value in selection: {selection.size}/"
            f"{selection.purpose}/{selection.desktop}"
        )


def resolve_install_set(plan: Plan, runner: CommandRunner) -> Resolution:
    """Split the plan's install set against live installed/available state."""
    wanted = plan.packages_install
    if not wanted:
        return Resolution((), (), (), True, True)
    installed = query_installed(runner)
    if installed is None:
        return Resolution((), (), (), False, False)
    skip = tuple(p for p in wanted if p in installed)
    missing = tuple(p for p in wanted if p not in installed)
    if not missing:
        return Resolution((), skip, (), True, True)
    available = check_available(runner, missing)
    if available is None:
        return Resolution((), skip, (), True, False)
    unavailable = tuple(p for p in missing if p not in available)
    return Resolution(
        install=tuple(p for p in missing if p in available),
        skip_installed=skip,
        unavailable=unavailable,
        state_known=True,
        availability_known=True,
    )


def manifest_name(started_at: datetime) -> str:
    # No status in the filename: lexical order is purely chronological, so
    # verify's "latest" is simply the last name.
    return started_at.strftime("%Y%m%dT%H%M%S") + "-1.json"


def write_manifest(env: ApplyEnv, manifest: Manifest) -> Path:
    """Persist a manifest under state_dir/manifests/, atomically."""
    directory = env.state_dir / "manifests"
    directory.mkdir(parents=True, exist_ok=True)
    base = manifest_name(env.now())
    path = directory / base
    serial = 1
    while path.exists():  # same-second collision -> deterministic suffix
        serial += 1
        path = directory / base.replace("-1.json", f"-{serial}.json")
    _write_manifest_file(path, manifest)
    return path


def _write_manifest_file(path: Path, manifest: Manifest) -> None:
    # Atomic on purpose: a torn manifest is worse than none.  0644 so a
    # non-root 'verify' can read what root wrote.
    text = manifest_to_json(manifest)
    fd, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.chmod(temp_name, 0o644)
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def _iso(moment: datetime) -> str:
    return moment.isoformat()


def _tail(text: str, limit: int = 2000) -> str:
    return text[-limit:].strip()


def apply_plan(
    plan: Plan, env: ApplyEnv, *, executor: Executor = APT_GET
) -> tuple[Manifest, Path]:
    """Execute a confirmed plan; returns (final manifest, manifest path).

    The pending manifest is written before the step runs so the intent
    record survives a crash, then the same file is rewritten with results.
    """
    if env.euid() != 0:
        raise NotRootError(
            "apply must run as root (try sudo); it refuses to elevate itself"
        )
    require_executable(plan)

    resolution = resolve_install_set(plan, env.runner)
    if not resolution.state_known:
        raise ApplyError(
            "dpkg-query: installed state unknown; refusing to apply "
            "without it (post-run verification would be impossible)"
        )
    if not resolution.availability_known:
        raise ApplyError("apt-cache: availability unknown; refusing to apply without it")
    if resolution.unavailable:
        raise PlanDriftError(
            "plan drifted: no longer available in the configured "
            "repositories: " + ", ".join(resolution.unavailable)
            + "; re-run 'debian-skeleton plan' and confirm a fresh plan"
        )

    started = env.now()
    warnings: list[str] = []
    if resolution.skip_installed:
        warnings.append(
            "skipped (already installed): " + ", ".join(resolution.skip_installed)
        )

    if not resolution.install:
        steps = ()
        if resolution.skip_installed:
            steps = (ApplyStep(
                "install", resolution.skip_installed, executor.name,
                "skipped", "already installed",
            ),)
        manifest = Manifest(
            schema_version=1,
            plan=plan,
            executor=executor.name,
            started_at=_iso(started),
            finished_at=_iso(env.now()),
            status="noop",
            steps=steps,
            warnings=tuple(warnings),
        )
        return manifest, write_manifest(env, manifest)

    pending = Manifest(
        schema_version=1,
        plan=plan,
        executor=executor.name,
        started_at=_iso(started),
        finished_at=None,
        status="pending",
        steps=(ApplyStep(
            "install", resolution.install, executor.name, "pending", ""
        ),),
        warnings=tuple(warnings),
    )
    path = write_manifest(env, pending)

    argv = executor.install_argv(resolution.install)
    try:
        result = env.runner.run(
            argv, timeout=INSTALL_TIMEOUT, env=dict(NONINTERACTIVE_ENV)
        )
        failure_note = _tail(result.stderr or result.stdout)
    except CommandError as exc:  # timeout / missing binary: nothing ran or it died
        result = None
        failure_note = f"{argv[0]}: {exc}"

    installed_after = query_installed(env.runner)
    landed = tuple(
        p for p in resolution.install
        if installed_after is not None and p in installed_after
    )
    if result is not None and result.returncode == 0 and len(landed) == len(resolution.install):
        step_status, detail = "ok", ""
    elif landed:
        step_status, detail = "partial", failure_note
    else:
        step_status = "failed"
        detail = failure_note or "no requested package landed"
        if result is not None and result.returncode != 0:
            detail += " (if dpkg reports an interrupted state, run: dpkg --configure -a)"

    step = ApplyStep("install", resolution.install, executor.name, step_status, detail)
    final = Manifest(
        schema_version=1,
        plan=plan,
        executor=executor.name,
        started_at=_iso(started),
        finished_at=_iso(env.now()),
        status={"ok": "applied", "partial": "partial", "failed": "failed"}[step_status],
        steps=(step,),
        warnings=tuple(warnings),
    )
    _write_manifest_file(path, final)  # rewrite the same file: intent -> record
    return final, path
