"""The interactive wizard: a Rich TUI over the same stages the CLI exposes.

Rich imports live in this module and nowhere else: the core stays
stdlib-only so probe/recommend/plan/apply/verify work on a fresh Debian
install before any repository is trusted (the wizard is opt-in via the
``tui`` extra).  Screens are plain functions over immutable models, and
the orchestrator drives probe -> recommend -> select -> plan -> confirm
-> apply-or-save, so every number shown is the number the apply layer
would act on.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from debian_skeleton.apply import (
    CONFIRM_PHRASE,
    ApplyEnv,
    ApplyError,
    apply_plan,
    phrase_ok,
)
from debian_skeleton.catalog.desktops import (
    WINDOW_MANAGERS,
    WM_REPLACEABLE,
    validate_selection,
)
from debian_skeleton.catalog.packages import PURPOSE_PACKAGES, SIZE_PACKAGES
from debian_skeleton.catalog.profiles import DESKTOPS
from debian_skeleton.models import (
    Plan,
    Probe,
    Recommendation,
    Selection,
    plan_to_json,
)
from debian_skeleton.planner import IncompatibleSelection, plan_selection
from debian_skeleton.probe import ProbeEnv, run_probe
from debian_skeleton.recommend import recommend
from debian_skeleton.report import format_bytes, format_kib
from debian_skeleton.runner import SubprocessRunner
from debian_skeleton.verify import verify_manifest


class Prompter(Protocol):
    """The seam tests drive; RichPrompter is the live implementation."""

    def ask(
        self, prompt: str, *,
        choices: tuple[str, ...] | None = None, default: str | None = None,
    ) -> str: ...

    def confirm(self, prompt: str, *, default: bool = False) -> bool: ...


@dataclass
class RichPrompter:
    console: Console

    def ask(
        self, prompt: str, *,
        choices: tuple[str, ...] | None = None, default: str | None = None,
    ) -> str:
        answer = Prompt.ask(
            prompt,
            choices=list(choices) if choices is not None else None,
            default=default,  # None keeps the prompt required
            console=self.console,
        )
        # rich returns the (None) default on empty input; the phrase loop
        # below wants a plain wrong answer to retry on.
        return "" if answer is None else str(answer)

    def confirm(self, prompt: str, *, default: bool = False) -> bool:
        # Not Confirm.ask: rich >= 15 accepts only literal y/n, while
        # Debian's python3-rich 13 also took yes/true/1.  Parsing here is
        # uniform across both, and every confirm's "no" is the safe branch,
        # so unrecognized junk reads as no.
        answer = Prompt.ask(
            f"{prompt} [y/n]",
            default="y" if default else "n",
            console=self.console,
        )
        return str(answer).strip().lower() in ("y", "yes", "true", "1", "on")


@dataclass
class WizardUI:
    """Everything a screen may touch: one console, one prompter."""

    console: Console
    prompter: Prompter

    def show(self, renderable: object) -> None:
        self.console.print(renderable)


# -- screens (pure functions over models; only the prompter talks) ----------------


def screen_probe(ui: WizardUI, probe: Probe) -> None:
    hardware = probe.hardware
    table = Table.grid(padding=(0, 2))
    table.add_row("distribution", probe.os.id or "unknown")
    table.add_row("version", probe.os.pretty_name or "unknown")
    table.add_row("architecture", hardware.architecture or "unknown")
    table.add_row("memory", format_kib(hardware.memory.total_kib))
    table.add_row(
        "root filesystem",
        f"{format_bytes(hardware.root_fs.available_bytes)} available",
    )
    verdict = {True: "yes", False: "no"}.get(hardware.is_laptop, "unknown")
    table.add_row("laptop", verdict)
    sessions = probe.installed.x_sessions + probe.installed.wayland_sessions
    table.add_row("graphical sessions", ", ".join(sessions) or "none")
    ui.show(Panel(table, title="This machine (probe)"))
    if probe.warnings:
        ui.console.print("[yellow]Probe warnings[/]")
        for warning in probe.warnings:
            ui.console.print(f"[yellow]- {warning}[/]")


def screen_recommendation(ui: WizardUI, recommendation: Recommendation) -> bool:
    """Show the suggestion; True = accept it as-is."""
    selection = recommendation.selection
    table = Table.grid(padding=(0, 2))
    table.add_row("size", selection.size)
    table.add_row("purpose", selection.purpose)
    table.add_row("desktop", selection.desktop)
    table.add_row("window manager", selection.window_manager or "automatic")
    ui.show(Panel(table, title="Recommendation"))
    ui.console.print("[bold]Reasons[/]")
    for reason in recommendation.reasons:
        ui.console.print(f"- {reason}")
    return ui.prompter.confirm("Accept this recommendation?", default=True)


def screen_selection(ui: WizardUI, recommended: Selection) -> Selection:
    """One question per axis; only compatible choices are ever offered."""
    size = ui.prompter.ask(
        "System size", choices=tuple(SIZE_PACKAGES), default=recommended.size
    )
    purpose = ui.prompter.ask(
        "Purpose", choices=tuple(PURPOSE_PACKAGES), default=recommended.purpose
    )
    desktop = ui.prompter.ask(
        "Graphical stack", choices=DESKTOPS, default=recommended.desktop
    )
    window_manager = None
    if desktop in WM_REPLACEABLE:
        answer = ui.prompter.ask(
            "Window manager",
            choices=("automatic", *WINDOW_MANAGERS),
            default="automatic",
        )
        window_manager = None if answer == "automatic" else answer
    selection = Selection(size, purpose, desktop, window_manager)
    ok, explanation = validate_selection(selection)  # defensive backstop:
    if not ok:  # the menus above never offer an incompatible combination
        raise IncompatibleSelection(explanation)
    return selection


def screen_plan(ui: WizardUI, plan: Plan) -> None:
    selection = plan.selection
    table = Table.grid(padding=(0, 2))
    table.add_row("size", selection.size)
    table.add_row("purpose", selection.purpose)
    table.add_row("desktop", selection.desktop)
    table.add_row("window manager", selection.window_manager or "automatic")
    ui.show(Panel(table, title="Plan"))
    ui.console.print(
        f"install ({len(plan.packages_install)}): "
        + (", ".join(plan.packages_install) or "none")
    )
    if plan.simulation is not None:
        ui.console.print(
            f"download ~{format_bytes(plan.simulation.download_bytes)}, "
            f"disk ~{format_bytes(plan.simulation.disk_estimate_bytes)}, "
            f"{len(plan.simulation.newly_installed)} new package(s) "
            "incl. dependencies"
        )
    ui.console.print("removes nothing; touches no config or services")
    for warning in plan.warnings:
        ui.console.print(f"[yellow]- {warning}[/]")


def screen_confirm_apply(ui: WizardUI, plan: Plan) -> bool:
    """The typed phrase, up to three attempts (same rule as the CLI)."""
    for _attempt in range(3):
        answer = ui.prompter.ask(
            f"Type '{CONFIRM_PHRASE}' to install "
            f"{len(plan.packages_install)} package(s)"
        )
        if phrase_ok(answer):
            return True
        ui.console.print("confirmation did not match; try again")
    return False


def screen_apply_or_save(ui: WizardUI) -> str:
    return ui.prompter.ask(
        "Next", choices=("apply now", "save plan", "abort"), default="save plan"
    )


# -- orchestrator ----------------------------------------------------------------


def _save(ui: WizardUI, plan: Plan) -> int:
    given = ui.prompter.ask(
        "Save plan to", default="debian-skeleton-plan.json"
    )
    path = Path(given).expanduser()
    if path.exists() and not ui.prompter.confirm(
        f"{path} exists; overwrite?", default=False
    ):
        ui.console.print("Aborted -- nothing was changed.")
        return 0
    path.write_text(plan_to_json(plan))
    ui.console.print(f"Plan saved to {path}")
    ui.console.print(f"Apply it later with: sudo debian-skeleton apply {path}")
    return 0


def _apply(ui: WizardUI, plan: Plan, env: ApplyEnv) -> int:
    # A spinner, not a progress bar: the runner captures apt's output, so a
    # streaming percentage would be theater until a streaming seam exists.
    with ui.console.status(
        f"apt-get install -- {len(plan.packages_install)} package(s) "
        "(this can take minutes)"
    ):
        try:
            manifest, path = apply_plan(plan, env)
        except ApplyError as exc:  # not root / drift / unknown: nothing ran
            ui.console.print(f"error: {exc}")
            return 3
    ui.console.print(f"[bold]{manifest.status}[/] -- manifest: {path}")
    for step in manifest.steps:
        ui.console.print(f"- {step.kind}: {step.status}")
        if step.detail:
            ui.console.print(f"  {step.detail.splitlines()[-1]}")
    if manifest.status in ("applied", "noop") and ui.prompter.confirm(
        "Verify now?", default=True
    ):
        report = verify_manifest(manifest, env.runner, manifest_path=str(path))
        ui.console.print(f"verify: {report.status}")
        return 0 if report.status == "satisfied" else 4
    return 0 if manifest.status in ("applied", "noop") else 4


def _run(
    ui: WizardUI, probe_env: ProbeEnv | None, apply_env: ApplyEnv | None
) -> int:
    env = probe_env or ProbeEnv(root=Path("/"), runner=SubprocessRunner())
    apply = apply_env or ApplyEnv()

    probe = run_probe(env)
    screen_probe(ui, probe)
    recommendation = recommend(probe)
    if screen_recommendation(ui, recommendation):
        selection = recommendation.selection
    else:
        selection = screen_selection(ui, recommendation.selection)

    plan = plan_selection(selection, probe, env.runner)  # real simulation:
    screen_plan(ui, plan)  # the same honest numbers the CLI shows
    action = screen_apply_or_save(ui)
    if action == "abort":
        ui.console.print("Aborted -- nothing was changed.")
        return 0
    if action == "save plan":
        return _save(ui, plan)
    if apply.euid() != 0:  # refuse before the phrase, never after typing it
        ui.console.print(
            "error: apply must run as root; re-run the wizard with sudo "
            "or choose 'save plan'"
        )
        return 3
    if not screen_confirm_apply(ui, plan):
        ui.console.print("error: confirmation declined; nothing was changed")
        return 3
    return _apply(ui, plan, apply)


def run_wizard(
    probe_env: ProbeEnv | None = None,
    apply_env: ApplyEnv | None = None,
    ui: WizardUI | None = None,
) -> int:
    """Drive the whole pipeline interactively; returns a CLI exit code."""
    console = Console()
    if ui is None:
        ui = WizardUI(console=console, prompter=RichPrompter(console))
    try:
        return _run(ui, probe_env, apply_env)
    except EOFError:  # Ctrl-D / closed stdin: the no-TTY story
        ui.console.print("\nAborted -- nothing was changed.")
        return 0
    except IncompatibleSelection as exc:
        ui.console.print(f"error: incompatible selection: {exc}")
        return 2
