"""Shared fixtures: build a ProbeEnv over a writable copy of a machine tree."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import pytest

from debian_skeleton.apply import ApplyEnv
from debian_skeleton.probe import ProbeEnv
from support import FakeStatvfs, ScriptedRunner

FIXTURES = Path(__file__).parent / "fixtures"

# A fixed clock makes manifest names and timestamps assertable.
FIXED_NOW = datetime(2026, 9, 28, 10, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def make_env(tmp_path: Path) -> Callable[[str], tuple[ProbeEnv, Path]]:
    """Return a factory: machine name -> (ProbeEnv over a tmp copy, root Path).

    The tree is copied so tests never mutate the recorded fixture, and so
    chmod-based unreadable-directory tests are safe.
    """

    def _make(machine: str) -> tuple[ProbeEnv, Path]:
        fixture = FIXTURES / machine
        root = tmp_path / machine
        shutil.copytree(fixture, root, ignore=shutil.ignore_patterns("commands"))
        commands = fixture / "commands"
        return (
            ProbeEnv(
                root=root,
                runner=ScriptedRunner.load(commands),
                statvfs=FakeStatvfs.load(commands),
            ),
            root,
        )

    return _make


@pytest.fixture
def make_apply_env(tmp_path: Path) -> Callable[..., ApplyEnv]:
    """Return a factory: machine name -> ApplyEnv with scripted commands.

    Rootless by test design (euid injectable), state in a tmp dir, and a
    fixed clock -- no test ever runs a real apt-get.
    """

    def _make(machine: str = "apply-bookworm", euid: int = 0) -> ApplyEnv:
        return ApplyEnv(
            state_dir=tmp_path / machine / "state",
            runner=ScriptedRunner.load(FIXTURES / machine / "commands"),
            euid=lambda: euid,
            now=lambda: FIXED_NOW,
        )

    return _make
