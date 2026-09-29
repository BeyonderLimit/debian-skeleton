"""Dependency-injection bundle and forgiving I/O for probe collectors.

Every collector receives a :class:`ProbeContext` built from a
:class:`ProbeEnv`.  The context centralizes the probe's safety rule: an
unreadable evidence source never crashes the run — it yields ``None`` plus a
``"source: message"`` warning.  All paths resolve as ``root / rel``, one
uniform mechanism for the live system (``/``) and fixture trees alike.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from debian_skeleton.runner import (
    CommandError,
    CommandResult,
    CommandRunner,
    SubprocessRunner,
)

# Callable with the signature of os.statvfs; fixtures inject a fake because a
# copied filesystem tree cannot fake statvfs results.
Statvfs = Callable[[Path], "os.statvfs_result"]


@dataclass(frozen=True)
class ProbeEnv:
    """Everything a collector may touch: a root path, a command runner, statvfs."""

    root: Path = Path("/")
    runner: CommandRunner = field(default_factory=SubprocessRunner)
    statvfs: Statvfs = os.statvfs


class ProbeContext:
    """Per-run mutable state: collected warnings plus forgiving I/O helpers."""

    def __init__(self, env: ProbeEnv) -> None:
        self.env = env
        self._warnings: list[str] = []

    # -- warnings ------------------------------------------------------

    def warn(self, source: str, message: str) -> None:
        self._warnings.append(f"{source}: {message}")

    @property
    def warnings(self) -> tuple[str, ...]:
        return tuple(self._warnings)

    # -- path helpers ----------------------------------------------------

    def _resolve(self, rel: str) -> Path:
        return self.env.root / rel

    def exists(self, rel: str) -> bool:
        return self._resolve(rel).exists()

    def read_text(self, rel: str) -> str | None:
        """Read a file whose absence or unreadability is worth a warning."""
        return self._read(rel, warn_if_missing=True)

    def read_optional_text(self, rel: str) -> str | None:
        """Read a file whose absence is normal (e.g. a per-battery ``type``)."""
        return self._read(rel, warn_if_missing=False)

    def _read(self, rel: str, *, warn_if_missing: bool) -> str | None:
        path = self._resolve(rel)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if warn_if_missing:
                self.warn(rel, "file not found")
            return None
        except OSError as exc:
            self.warn(rel, f"unreadable: {exc.strerror or exc}")
            return None

    def list_dir(
        self, rel: str, *, warn_if_missing: bool = False
    ) -> tuple[Path, ...] | None:
        """List a directory; ``None`` means absent (optionally warned) or unreadable."""
        path = self._resolve(rel)
        try:
            return tuple(sorted(path.iterdir()))
        except FileNotFoundError:
            if warn_if_missing:
                self.warn(rel, "directory not found")
            return None
        except OSError as exc:
            self.warn(rel, f"unreadable: {exc.strerror or exc}")
            return None

    # -- command / statvfs seams ------------------------------------------

    def run(self, argv: Sequence[str], *, timeout: float = 10.0) -> CommandResult | None:
        """Run a command; ``None`` (plus a warning) when it could not run."""
        try:
            return self.env.runner.run(argv, timeout=timeout)
        except CommandError as exc:
            self.warn(" ".join(argv), str(exc))
            return None

    def statvfs_root(self) -> os.statvfs_result | None:
        try:
            return self.env.statvfs(self.env.root)
        except OSError as exc:
            self.warn("statvfs", f"failed on {self.env.root}: {exc.strerror or exc}")
            return None
