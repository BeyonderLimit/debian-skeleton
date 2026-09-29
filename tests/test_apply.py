from __future__ import annotations

import json
from pathlib import Path

import pytest

from debian_skeleton.apply import (
    APT_GET,
    ApplyEnv,
    NotRootError,
    PlanDriftError,
    apply_plan,
    manifest_name,
    phrase_ok,
    require_executable,
    resolve_install_set,
    write_manifest,
)
from debian_skeleton.apt import DPKG_QUERY_ARGV
from debian_skeleton.models import ApplyStep, Manifest, Plan, Selection
from debian_skeleton.planner import IncompatibleSelection
from debian_skeleton.runner import CommandResult
from support import ScriptedRunner

from conftest import FIXED_NOW


def env_with(runner: ScriptedRunner, state_dir: Path) -> ApplyEnv:
    """A rootless-by-test env: fixed clock, scripted commands, tmp state."""
    return ApplyEnv(
        state_dir=state_dir, runner=runner,
        euid=lambda: 0, now=lambda: FIXED_NOW,
    )

STANDARD_PLAN = Plan(
    selection=Selection("standard", "daily", "none", None),
    packages_install=("bash-completion", "curl", "less", "rsync", "xdg-utils"),
)


def _dpkg(stdout: str) -> CommandResult:
    return CommandResult(
        argv=("dpkg-query",), returncode=0, stdout=stdout, stderr=""
    )


def _policy(stdout: str) -> CommandResult:
    return CommandResult(
        argv=("apt-cache", "policy"), returncode=0, stdout=stdout, stderr=""
    )


RSYNC_POLICY = "rsync:\n  Installed: (none)\n  Candidate: 3.2.7-1\n"
CURL_POLICY = "curl:\n  Installed: (none)\n  Candidate: 7.88.1-1\n"


# -- gates -----------------------------------------------------------------------


def test_apply_refuses_without_root_and_writes_nothing(make_apply_env):
    env = make_apply_env(euid=1000)

    with pytest.raises(NotRootError, match="root"):
        apply_plan(STANDARD_PLAN, env)

    assert not (env.state_dir / "manifests").exists()


def test_phrase_ok_is_exact_and_case_sensitive():
    assert phrase_ok("apply")
    assert not phrase_ok("APPLY")
    assert not phrase_ok("apply ")  # trailing space
    assert not phrase_ok(" yes ")


def test_require_executable_rejects_incompatible_and_unknown_axes():
    with pytest.raises(IncompatibleSelection):
        require_executable(Plan(
            selection=Selection("minimal", "daily", "labwc", "openbox"),
            packages_install=(),
        ))
    with pytest.raises(IncompatibleSelection, match="unknown axis"):
        require_executable(Plan(
            selection=Selection("huge", "daily", "none", None),
            packages_install=(),
        ))


# -- resolve_install_set truth table -----------------------------------------------


def test_resolve_with_empty_plan_never_asks_the_machine():
    resolution = resolve_install_set(
        Plan(selection=Selection("minimal", "daily", "none", None),
             packages_install=()),
        ScriptedRunner({}),
    )
    assert resolution.install == ()
    assert resolution.state_known and resolution.availability_known


def test_resolve_splits_installed_missing_and_unavailable():
    runner = ScriptedRunner({
        DPKG_QUERY_ARGV: _dpkg("curl\tii \n"),
        ("apt-cache", "policy"): _policy(RSYNC_POLICY),
    })
    resolution = resolve_install_set(STANDARD_PLAN, runner)
    assert resolution.skip_installed == ("curl",)
    assert resolution.install == ("rsync",)  # available, not installed
    assert resolution.unavailable == ("bash-completion", "less", "xdg-utils")
    assert resolution.state_known and resolution.availability_known


def test_resolve_flags_unknown_installed_state():
    resolution = resolve_install_set(STANDARD_PLAN, ScriptedRunner({}))
    assert not resolution.state_known


def test_resolve_flags_unknown_availability():
    runner = ScriptedRunner({
        DPKG_QUERY_ARGV: _dpkg(""),  # nothing installed; policy unmapped
    })
    resolution = resolve_install_set(STANDARD_PLAN, runner)
    assert resolution.state_known
    assert not resolution.availability_known


# -- the run ------------------------------------------------------------------------


def test_successful_apply_writes_pending_then_final_manifest(make_apply_env):
    env = make_apply_env("apply-bookworm")

    manifest, path = apply_plan(STANDARD_PLAN, env)

    assert manifest.status == "applied"
    assert manifest.steps == (
        ApplyStep("install", ("rsync", "xdg-utils"), "apt-get", "ok", ""),
    )
    assert any("already installed" in w for w in manifest.warnings)
    assert path.name == "20260928T101500-1.json"
    # what landed on disk is the final record, with a finish time
    on_disk = json.loads(path.read_text())
    assert on_disk["status"] == "applied"
    assert on_disk["finished_at"] is not None
    assert not list(path.parent.glob("*.tmp"))  # atomic write left no debris


def test_apply_sends_noninteractive_environment(make_apply_env):
    env = make_apply_env("apply-bookworm")

    apply_plan(STANDARD_PLAN, env)

    assert {"DEBIAN_FRONTEND": "noninteractive"} in env.runner.seen_env


def test_re_run_is_a_noop_that_never_touches_apt(tmp_path):
    # everything already installed; the runner has NO apt records at all,
    # so an attempted install would raise CommandError and fail the test
    runner = ScriptedRunner({
        DPKG_QUERY_ARGV: _dpkg(
            "bash-completion\tii \ncurl\tii \nless\tii \n"
            "rsync\tii \nxdg-utils\tii \n"
        )
    })

    manifest, _path = apply_plan(STANDARD_PLAN, env_with(runner, tmp_path / "s"))

    assert manifest.status == "noop"
    assert manifest.steps[0].status == "skipped"


def test_unavailable_package_refuses_before_any_write(tmp_path):
    runner = ScriptedRunner({
        DPKG_QUERY_ARGV: _dpkg(""),  # nothing installed
        ("apt-cache", "policy"): _policy(""),  # nothing available anywhere
    })
    env = env_with(runner, tmp_path / "s")

    with pytest.raises(PlanDriftError, match="drifted"):
        apply_plan(STANDARD_PLAN, env)

    assert not (env.state_dir / "manifests").exists()


def test_failed_install_records_stderr_tail(make_apply_env):
    env = make_apply_env("apply-broken")
    plan = Plan(selection=Selection("minimal", "daily", "none", None),
                packages_install=("rsync",))

    manifest, path = apply_plan(plan, env)

    assert manifest.status == "failed"
    assert manifest.steps[0].status == "failed"
    assert "Unable to correct problems" in manifest.steps[0].detail
    assert json.loads(path.read_text())["status"] == "failed"


def test_partial_landing_is_reported_as_partial(tmp_path):
    runner = ScriptedRunner({
        DPKG_QUERY_ARGV: [
            _dpkg(""),                                # pre: nothing installed
            _dpkg("curl\tii \n"),                     # post: only curl landed
        ],
        ("apt-cache", "policy"): _policy(RSYNC_POLICY + CURL_POLICY),
        ("apt-get", "--yes"): CommandResult(
            argv=("apt-get", "--yes"), returncode=0,
            stdout="Setting up curl ...\n", stderr="",
        ),
    })
    plan = Plan(selection=Selection("minimal", "daily", "none", None),
                packages_install=("curl", "rsync"))

    manifest, _path = apply_plan(plan, env_with(runner, tmp_path / "s"))

    assert manifest.status == "partial"
    assert manifest.steps[0].status == "partial"


def test_missing_install_command_is_a_failed_step_not_a_crash(tmp_path):
    runner = ScriptedRunner({
        DPKG_QUERY_ARGV: _dpkg(""),
        ("apt-cache", "policy"): _policy(RSYNC_POLICY),
        # no apt-get record: the runner raises CommandError for the install
    })
    plan = Plan(selection=Selection("minimal", "daily", "none", None),
                packages_install=("rsync",))

    manifest, _path = apply_plan(plan, env_with(runner, tmp_path / "s"))

    assert manifest.status == "failed"
    assert "apt-get" in manifest.steps[0].detail


# -- manifest naming/persistence -----------------------------------------------------


def test_manifest_name_is_timestamped():
    assert manifest_name(FIXED_NOW) == "20260928T101500-1.json"


def test_write_manifest_suffixes_same_second_collisions(make_apply_env):
    env = make_apply_env()
    manifest = Manifest(
        schema_version=1,
        plan=STANDARD_PLAN,
        executor=APT_GET.name,
        started_at=FIXED_NOW.isoformat(),
        finished_at=None,
        status="pending",
        steps=(ApplyStep("install", ("rsync",), "apt-get", "pending", ""),),
    )

    first = write_manifest(env, manifest)
    second = write_manifest(env, manifest)

    assert first.name == "20260928T101500-1.json"
    assert second.name == "20260928T101500-2.json"
