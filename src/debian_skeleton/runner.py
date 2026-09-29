"""Command execution seam.

Infrastructure shared by every stage that runs external commands (probe
today, APT simulation later).  A runner turns an argv into a
:class:`CommandResult` value, or raises :class:`CommandError` for
*infrastructure* failures (missing binary, timeout, deliberately skipped).
A non-zero exit code is data the caller inspects, never an exception.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


class CommandError(RuntimeError):
    """The command could not run at all: missing binary, timeout, or skipped."""


class CommandRunner(Protocol):
    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float = 10.0,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult: ...


class SubprocessRunner:
    """Run commands on the live system via :mod:`subprocess`."""

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float = 10.0,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        command = tuple(argv)
        # Merge over the inherited environment, never replace it: PATH,
        # locale, and proxy settings must survive for apt to work.
        merged: Mapping[str, str] | None = (
            None if env is None else {**os.environ, **env}
        )
        try:
            proc = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=merged,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise CommandError(f"{command[0]}: {exc}") from exc
        return CommandResult(
            argv=command,
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )


class OfflineRunner:
    """Refuse every command: used when probing a non-live root.

    ``dpkg``/``lsblk`` always describe the live host (util-linux 2.38 has no
    ``--sysroot``), so a fixture probe must not silently mix host data in.
    """

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float = 10.0,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        raise CommandError(
            f"skipped: commands are disabled for non-live root ({argv[0]})"
        )
