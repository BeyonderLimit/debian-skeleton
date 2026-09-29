from __future__ import annotations

import json
import os
import sys

import pytest

import debian_skeleton.cli as cli
from debian_skeleton.cli import main
from debian_skeleton.models import (
    ApplyStep,
    Manifest,
    Plan,
    Selection,
    manifest_to_json,
    plan_to_dict,
    plan_to_json,
)


def test_probe_on_live_machine_outputs_report(capsys):
    code = main(("probe",))
    out = capsys.readouterr().out
    assert code == 0
    assert "OS" in out
    assert "is laptop" in out
    assert "Warnings" in out


def test_probe_json_on_live_machine_parses(capsys):
    code = main(("probe", "--json"))
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert set(payload) == {"root", "os", "hardware", "installed", "warnings"}


def test_probe_with_root_fixture_disables_commands(capsys, make_env):
    _env, root = make_env("degraded")

    code = main(("probe", "--json", "--root", str(root)))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["os"]["id"] is None
    assert any("skipped" in warning for warning in payload["warnings"])


def test_probe_root_must_exist():
    with pytest.raises(SystemExit) as excinfo:
        main(("probe", "--root", "/nonexistent-debian-skeleton-dir"))
    assert excinfo.value.code == 2


def test_missing_subcommand_prints_help_and_fails(capsys):
    assert main(()) == 2
    assert "probe" in capsys.readouterr().err


def test_unknown_subcommand_fails():
    with pytest.raises(SystemExit) as excinfo:
        main(("bogus",))
    assert excinfo.value.code == 2


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        main(("--help",))
    assert excinfo.value.code == 0
    assert "probe" in capsys.readouterr().out


# -- recommend -----------------------------------------------------------------


def test_recommend_on_live_machine_outputs_selection(capsys):
    code = main(("recommend",))
    out = capsys.readouterr().out
    assert code == 0
    assert "Recommendation" in out
    assert "Reasons" in out


def test_recommend_json_parses_with_warnings(capsys):
    code = main(("recommend", "--json"))
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert set(payload) == {"selection", "reasons", "warnings"}
    assert set(payload["selection"]) == {"size", "purpose", "desktop", "window_manager"}


def test_recommend_with_root_fixture(make_env, capsys):
    _env, root = make_env("server-minimal")

    code = main(("recommend", "--json", "--root", str(root)))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["selection"]["size"] == "minimal"
    assert payload["selection"]["desktop"] == "none"


# -- plan ------------------------------------------------------------------------


def test_plan_on_live_machine_minimal_none_is_clean(capsys):
    code = main(("plan", "--size", "minimal", "--purpose", "daily", "--desktop", "none"))
    out = capsys.readouterr().out

    assert code == 0
    assert "Plan" in out
    assert "Install" in out
    assert "removes nothing" in out
    assert "nothing will be changed" in out


def test_plan_on_live_machine_simulates_with_real_apt(capsys):
    code = main(("plan", "--size", "standard", "--desktop", "xfce"))
    out = capsys.readouterr().out

    assert code == 0
    assert "download" in out
    assert "disk estimate" in out


def test_plan_defaults_come_from_the_recommendation(capsys):
    code = main(("plan",))
    out = capsys.readouterr().out

    assert code == 0
    assert "# from recommendation:" in out


def test_plan_json_shape(capsys):
    code = main(("plan", "--json", "--size", "minimal", "--desktop", "none"))
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert set(payload) == {
        "selection", "packages_install", "packages_remove",
        "config_changes", "warnings", "simulation",
    }


def test_plan_incompatible_selection_exits_two_with_explanation(capsys):
    code = main(("plan", "--desktop", "labwc", "--window-manager", "openbox"))
    err = capsys.readouterr().err

    assert code == 2
    assert "incompatible selection" in err


def test_plan_unknown_desktop_choice_exits_two():
    with pytest.raises(SystemExit) as excinfo:
        main(("plan", "--desktop", "gnome"))
    assert excinfo.value.code == 2


def test_plan_no_apt_reports_the_skip(make_env, capsys):
    _env, root = make_env("laptop-bookworm")

    code = main((
        "plan", "--size", "standard", "--desktop", "xfce",
        "--root", str(root), "--no-apt",
    ))
    out = capsys.readouterr().out

    assert code == 0
    assert "apt checks skipped (--no-apt)" in out


def test_plan_with_foreign_root_degrades_to_unresolved(make_env, capsys):
    _env, root = make_env("laptop-bookworm")

    code = main(("plan", "--size", "standard", "--desktop", "xfce", "--root", str(root)))
    out = capsys.readouterr().out

    assert code == 0
    assert "unresolved" in out


def test_plan_with_foreign_root_minimal_none_needs_no_apt(make_env, capsys):
    _env, root = make_env("server-minimal")

    code = main(("plan", "--root", str(root)))
    out = capsys.readouterr().out

    assert code == 0
    assert "Warnings" in out


# -- apply ------------------------------------------------------------------------


class _FakeTty:
    def isatty(self) -> bool:
        return True


def _write_plan(tmp_path, plan: Plan) -> str:
    path = tmp_path / "plan.json"
    path.write_text(plan_to_json(plan))
    return str(path)


def _minimal_plan(packages: tuple[str, ...]) -> Plan:
    return Plan(
        selection=Selection("minimal", "daily", "none", None),
        packages_install=packages,
    )


def test_apply_missing_plan_file_exits_two():
    with pytest.raises(SystemExit) as excinfo:
        main(("apply", "/nonexistent-debian-skeleton-plan.json"))
    assert excinfo.value.code == 2


def test_apply_malformed_plan_exits_two(capsys, tmp_path):
    path = tmp_path / "plan.json"
    path.write_text("{not json")

    assert main(("apply", str(path))) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_apply_plan_with_removals_exits_two(capsys, tmp_path):
    document = plan_to_dict(_minimal_plan(()))
    document["packages_remove"] = ["xfce4"]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(document))

    assert main(("apply", str(path))) == 2
    assert "never removes" in capsys.readouterr().err


def test_apply_incompatible_selection_in_file_exits_two(capsys, tmp_path):
    plan = Plan(
        selection=Selection("minimal", "daily", "labwc", "openbox"),
        packages_install=(),
    )
    path = _write_plan(tmp_path, plan)

    assert main(("apply", str(path))) == 2
    assert "not executable" in capsys.readouterr().err


def test_apply_not_root_exits_three(capsys, tmp_path, monkeypatch):
    path = _write_plan(tmp_path, _minimal_plan(("curl",)))
    monkeypatch.setattr(os, "geteuid", lambda: 1000)

    code = main(("apply", path, "--yes", "--state-dir", str(tmp_path / "s")))

    assert code == 3
    assert "root" in capsys.readouterr().err


def test_apply_without_tty_or_yes_exits_three(capsys, tmp_path, monkeypatch):
    path = _write_plan(tmp_path, _minimal_plan(("curl",)))
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    # pytest's stdin is already not a TTY

    code = main(("apply", path, "--state-dir", str(tmp_path / "s")))

    assert code == 3
    assert "--yes" in capsys.readouterr().err


def test_apply_wrong_phrase_three_times_declines(capsys, tmp_path, monkeypatch):
    path = _write_plan(tmp_path, _minimal_plan(("curl",)))
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(sys, "stdin", _FakeTty())
    monkeypatch.setattr(cli, "_read_phrase", lambda prompt: "nope")

    code = main(("apply", path, "--state-dir", str(tmp_path / "s")))
    err = capsys.readouterr().err

    assert code == 3
    assert "declined" in err
    assert not (tmp_path / "s" / "manifests").exists()


def test_apply_scripted_success_exits_zero(capsys, tmp_path, monkeypatch, make_apply_env):
    path = _write_plan(tmp_path, Plan(
        selection=Selection("standard", "daily", "none", None),
        packages_install=("rsync", "xdg-utils"),
    ))
    env = make_apply_env("apply-bookworm")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli, "_build_apply_env", lambda args: env)

    code = main(("apply", path, "--yes", "--state-dir", str(env.state_dir)))
    out = capsys.readouterr().out

    assert code == 0
    assert "skipping confirmation (--yes)" in out
    assert "status            applied" in out
    assert "manifest" in out


def test_apply_scripted_failure_exits_four(capsys, tmp_path, monkeypatch, make_apply_env):
    path = _write_plan(tmp_path, _minimal_plan(("rsync",)))
    env = make_apply_env("apply-broken")
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setattr(cli, "_build_apply_env", lambda args: env)

    code = main(("apply", path, "--yes", "--state-dir", str(env.state_dir)))

    assert code == 4
    assert "failed" in capsys.readouterr().out


def test_apply_dry_run_on_live_machine_is_read_only(capsys, tmp_path):
    path = _write_plan(tmp_path, _minimal_plan(("curl",)))

    code = main(("apply", path, "--dry-run"))
    out = capsys.readouterr().out

    assert code == 0
    assert "Dry run -- nothing will be changed" in out
    assert "never removed" in out


# -- verify -------------------------------------------------------------------------


def test_verify_with_no_manifests_exits_two(capsys, tmp_path):
    code = main(("verify", "--state-dir", str(tmp_path)))

    assert code == 2
    assert "no manifest" in capsys.readouterr().err


def test_verify_live_satisfied_exits_zero(capsys, tmp_path):
    # curl is installed on this machine (the live plan run proved it)
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    manifest = Manifest(
        schema_version=1,
        plan=_minimal_plan(("curl",)),
        executor="apt-get",
        started_at="2026-09-28T10:15:00+00:00",
        finished_at="2026-09-28T10:15:42+00:00",
        status="applied",
        steps=(ApplyStep("install", ("curl",), "apt-get", "ok", ""),),
    )
    path = manifests / "20260928T101500-1.json"
    path.write_text(manifest_to_json(manifest))

    code = main(("verify", str(path)))

    assert code == 0
    assert "satisfied" in capsys.readouterr().out


def test_verify_live_missing_package_exits_four(capsys, tmp_path):
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    manifest = Manifest(
        schema_version=1,
        plan=_minimal_plan(("debian-skeleton-no-such-pkg",)),
        executor="apt-get",
        started_at="2026-09-28T10:15:00+00:00",
        finished_at="2026-09-28T10:15:42+00:00",
        status="applied",
        steps=(ApplyStep("install", ("debian-skeleton-no-such-pkg",), "apt-get", "ok", ""),),
    )
    path = manifests / "20260928T101500-1.json"
    path.write_text(manifest_to_json(manifest))

    code = main(("verify", str(path)))

    assert code == 4
    assert "incomplete" in capsys.readouterr().out


# -- wizard ---------------------------------------------------------------------------


def test_wizard_without_rich_prints_install_guidance(capsys, monkeypatch):
    # Simulate a rich-less machine.  rich=None blocks the import chain, but
    # every cached rich.* submodule must go too: test_wizard.py imports rich
    # at collection time, and a half-cached package errors differently.
    for name in list(sys.modules):
        if name == "rich" or name.startswith("rich."):
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setitem(sys.modules, "rich", None)
    monkeypatch.delitem(sys.modules, "debian_skeleton.wizard", raising=False)

    code = main(("wizard",))
    err = capsys.readouterr().err

    assert code == 1
    assert "needs rich" in err
