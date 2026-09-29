"""Command-line entry point: ``debian-skeleton <subcommand>``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from debian_skeleton.apply import (
    CONFIRM_PHRASE,
    DEFAULT_STATE_DIR,
    ApplyError,
    apply_plan,
    phrase_ok,
    require_executable,
    resolve_install_set,
)
from debian_skeleton.catalog.desktops import WINDOW_MANAGERS, validate_selection
from debian_skeleton.catalog.packages import PURPOSE_PACKAGES, SIZE_PACKAGES
from debian_skeleton.catalog.profiles import DESKTOPS
from debian_skeleton.models import (
    PlanFormatError,
    Selection,
    manifest_from_dict,
    manifest_to_json,
    plan_from_dict,
    plan_to_json,
    probe_to_json,
    recommendation_to_json,
)
from debian_skeleton.planner import IncompatibleSelection, plan_selection
from debian_skeleton.probe import ProbeEnv, run_probe
from debian_skeleton.recommend import recommend
from debian_skeleton.report import (
    render_apply_result,
    render_plan,
    render_probe,
    render_recommendation,
    render_verify,
)
from debian_skeleton.runner import OfflineRunner, SubprocessRunner
from debian_skeleton.verify import find_latest_manifest, report_to_json, verify_manifest


def _existing_directory(value: str) -> Path:
    path = Path(value)
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"not an existing directory: {value}")
    return path


def _existing_file(value: str) -> Path:
    path = Path(value)
    if not path.is_file():
        raise argparse.ArgumentTypeError(f"not an existing file: {value}")
    return path


def _register_probe(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "probe", help="inspect the installed system (read-only)"
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    parser.add_argument(
        "--root",
        type=_existing_directory,
        default=Path("/"),
        metavar="PATH",
        help="probe a different filesystem tree (external commands are disabled)",
    )
    parser.set_defaults(handler=_cmd_probe)


def _build_env(args: argparse.Namespace) -> ProbeEnv:
    """One env per invocation: live root runs real commands, else offline."""
    is_live = args.root == Path("/")
    return ProbeEnv(
        root=args.root,
        runner=SubprocessRunner() if is_live else OfflineRunner(),
    )


def _cmd_probe(args: argparse.Namespace) -> int:
    probe = run_probe(_build_env(args))
    if args.json:
        print(probe_to_json(probe), end="")
    else:
        print(render_probe(probe), end="")
    return 0  # warnings are data, not failures


def _register_recommend(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "recommend", help="suggest size, purpose, and graphical stack (read-only)"
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    parser.add_argument(
        "--root",
        type=_existing_directory,
        default=Path("/"),
        metavar="PATH",
        help="probe a different filesystem tree (external commands are disabled)",
    )
    parser.set_defaults(handler=_cmd_recommend)


def _cmd_recommend(args: argparse.Namespace) -> int:
    probe = run_probe(_build_env(args))
    result = recommend(probe)
    if args.json:
        payload = json.loads(recommendation_to_json(result))
        payload["warnings"] = list(probe.warnings)
        print(json.dumps(payload, indent=2))
    else:
        print(render_recommendation(result), end="")
        _print_probe_warnings(probe)
    return 0


def _print_probe_warnings(probe) -> None:
    if probe.warnings:
        print("Probe warnings")
        for warning in probe.warnings:
            print(f"  - {warning}")
        print()


def _register_plan(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "plan", help="resolve a selection into a change plan (read-only)"
    )
    parser.add_argument(
        "--size", choices=tuple(SIZE_PACKAGES), help="system size profile"
    )
    parser.add_argument(
        "--purpose", choices=tuple(PURPOSE_PACKAGES), help="intended use"
    )
    parser.add_argument(
        "--desktop", choices=DESKTOPS, help="graphical stack"
    )
    parser.add_argument(
        "--window-manager",
        choices=WINDOW_MANAGERS,
        help="window manager override (only some desktops permit it)",
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    parser.add_argument(
        "--root",
        type=_existing_directory,
        default=Path("/"),
        metavar="PATH",
        help="probe a different filesystem tree (external commands are disabled)",
    )
    parser.add_argument(
        "--no-apt", action="store_true", help="skip APT simulation"
    )
    parser.set_defaults(handler=_cmd_plan)


def _cmd_plan(args: argparse.Namespace) -> int:
    env = _build_env(args)
    probe = run_probe(env)
    recommended = recommend(probe).selection
    given = {"size": args.size, "purpose": args.purpose,
             "desktop": args.desktop, "window_manager": args.window_manager}
    selection = Selection(
        size=args.size or recommended.size,
        purpose=args.purpose or recommended.purpose,
        desktop=args.desktop or recommended.desktop,
        window_manager=args.window_manager or recommended.window_manager,
    )
    ok, explanation = validate_selection(selection)
    if not ok:
        print(f"error: incompatible selection: {explanation}", file=sys.stderr)
        return 2
    result = plan_selection(
        selection, probe, env.runner, simulate=not args.no_apt
    )
    if args.json:
        print(plan_to_json(result), end="")
    else:
        defaulted = [axis for axis, value in given.items() if value is None]
        if defaulted:
            print(f"# from recommendation: {', '.join(defaulted)}")
            print()
        print(render_plan(result), end="")
        _print_probe_warnings(probe)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="debian-skeleton",
        description=(
            "TTY-first post-install Debian configurator: probe, recommend, "
            "plan (read-only), then apply a confirmed plan and verify it."
        ),
        epilog=(
            "exit codes: 0 success | 1 unexpected error | 2 invalid input | "
            "3 refused before any change | 4 not converged"
        ),
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")
    _register_probe(subparsers)
    _register_recommend(subparsers)
    _register_plan(subparsers)
    _register_apply(subparsers)
    _register_verify(subparsers)
    _register_wizard(subparsers)
    # doctor registers here in a later milestone
    return parser


# -- apply ------------------------------------------------------------------------


def _read_phrase(prompt: str) -> str:
    """Seam for tests: how the confirmation phrase is read (default: input)."""
    return input(prompt)


def _load_plan_file(path: Path):
    try:
        document = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise PlanFormatError(f"{path}: not valid JSON ({exc})") from exc
    return plan_from_dict(document)


def _build_apply_env(args: argparse.Namespace):
    """Live-only env: real runner, real euid/clock; state dir from --state-dir."""
    from debian_skeleton.apply import ApplyEnv

    return ApplyEnv(state_dir=args.state_dir)


def _register_apply(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "apply",
        help="execute a saved plan (needs root and a typed confirmation)",
    )
    parser.add_argument(
        "plan", type=_existing_file, metavar="PLAN",
        help="plan JSON file (from 'plan --json' or the wizard's save path)",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="skip the typed confirmation (explicit plan file only; "
             "root/drift checks still run)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="show what apply would do right now; writes nothing, needs no root",
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    parser.add_argument(
        "--state-dir", type=Path, default=DEFAULT_STATE_DIR, metavar="PATH",
        help=f"manifest directory (default: {DEFAULT_STATE_DIR})",
    )
    parser.set_defaults(handler=_cmd_apply)


def _cmd_apply(args: argparse.Namespace) -> int:
    try:
        plan = _load_plan_file(args.plan)
    except PlanFormatError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        require_executable(plan)
    except IncompatibleSelection as exc:
        print(f"error: plan is not executable: {exc}", file=sys.stderr)
        return 2

    env = _build_apply_env(args)

    if args.dry_run:
        return _dry_run(plan, env)

    # Refusal order matters: never make the user type the phrase into a
    # run that will then refuse on root.
    if os.geteuid() != 0:
        print(
            "error: apply must run as root (try sudo); "
            "it refuses to elevate itself",
            file=sys.stderr,
        )
        return 3

    if args.yes:
        print("skipping confirmation (--yes)")
    else:
        if not sys.stdin.isatty():
            print(
                "error: confirmation needs a TTY; review the plan, "
                "then re-run with --yes",
                file=sys.stderr,
            )
            return 3
        print(render_plan(plan), end="")
        for _attempt in range(3):
            answer = _read_phrase(
                f"Type '{CONFIRM_PHRASE}' to install "
                f"{len(plan.packages_install)} package(s): "
            )
            if phrase_ok(answer):
                break
            print("confirmation did not match; try again")
        else:
            print("error: confirmation declined; nothing was changed", file=sys.stderr)
            return 3

    try:
        manifest, path = apply_plan(plan, env)
    except ApplyError as exc:  # not root / drift / unknown state: nothing ran
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if args.json:
        print(manifest_to_json(manifest), end="")
    else:
        print(render_apply_result(manifest, str(path)))
    return 0 if manifest.status in ("applied", "noop") else 4


def _dry_run(plan, env) -> int:
    resolution = resolve_install_set(plan, env.runner)
    print("Dry run -- nothing will be changed.")
    if not resolution.state_known:
        print("  installed state: unknown (dpkg-query did not answer)")
    if not resolution.availability_known:
        print("  availability:    unknown (apt-cache policy did not answer)")
    if resolution.unavailable:
        print(
            "  no longer available: " + ", ".join(resolution.unavailable)
            + "  -> re-run 'debian-skeleton plan'"
        )
    print("  would install:   " + (", ".join(resolution.install) or "none"))
    print(
        "  already present: "
        + (", ".join(resolution.skip_installed) or "none")
        + " (skipped, never removed)"
    )
    if resolution.unavailable or not resolution.state_known:
        return 3
    return 0


# -- verify --------------------------------------------------------------------------


def _register_verify(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "verify",
        help="check the last (or a given) manifest against the machine (read-only)",
    )
    parser.add_argument(
        "manifest", type=_existing_file, metavar="MANIFEST", nargs="?",
        help="manifest file (default: the latest under --state-dir)",
    )
    parser.add_argument(
        "--json", action="store_true", help="machine-readable output"
    )
    parser.add_argument(
        "--state-dir", type=Path, default=DEFAULT_STATE_DIR, metavar="PATH",
        help=f"manifest directory (default: {DEFAULT_STATE_DIR})",
    )
    parser.set_defaults(handler=_cmd_verify)


def _cmd_verify(args: argparse.Namespace) -> int:
    path = args.manifest or find_latest_manifest(args.state_dir)
    if path is None:
        print(
            f"error: no manifest found under {args.state_dir}; "
            "run 'apply' first or pass a MANIFEST file",
            file=sys.stderr,
        )
        return 2
    try:
        manifest = manifest_from_dict(json.loads(path.read_text()))
    except (json.JSONDecodeError, PlanFormatError) as exc:
        print(f"error: {path}: {exc}", file=sys.stderr)
        return 2
    report = verify_manifest(manifest, SubprocessRunner(), manifest_path=str(path))
    if args.json:
        print(report_to_json(report), end="")
    else:
        print(render_verify(report), end="")
    return 0 if report.status == "satisfied" else 4


# -- wizard --------------------------------------------------------------------------


def _import_wizard():
    """Lazy import: cli.py stays stdlib-only; rich is an optional extra.

    Returns the wizard entry point, or None after printing install
    guidance (an environment problem, not a usage error -> exit 1).
    """
    try:
        from debian_skeleton.wizard import run_wizard
    except ImportError:
        print(
            "error: the wizard needs rich; install with "
            "'pip install \".[tui]\"' or 'apt install python3-rich'",
            file=sys.stderr,
        )
        return None
    return run_wizard


def _register_wizard(subparsers: "argparse._SubParsersAction") -> None:
    parser = subparsers.add_parser(
        "wizard",
        help="interactive Rich TUI: probe, recommend, select, plan, apply or save",
    )
    parser.set_defaults(handler=_cmd_wizard)


def _cmd_wizard(_args: argparse.Namespace) -> int:
    run_wizard = _import_wizard()
    if run_wizard is None:
        return 1
    return run_wizard()


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return handler(args)
    except Exception as exc:  # TTY contract: never dump a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1
