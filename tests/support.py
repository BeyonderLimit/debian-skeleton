"""Shared test infrastructure (test-only; not shipped)."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace

from debian_skeleton.runner import CommandError, CommandResult

# Used when a fixture records no statvfs.json of its own.
STATVFS_DEFAULTS = {
    "f_bsize": 4096,
    "f_blocks": 26214400,  # 100 GiB
    "f_bfree": 13107200,  # 50 GiB
    "f_bavail": 11534336,  # 44 GiB
}


class ScriptedRunner:
    """Replay canned command results, matched by longest argv prefix.

    Records are JSON files under a fixture's ``commands/`` directory:
    ``{"program": "dpkg", "stdout": "amd64\\n"}`` (matched by program name)
    or ``{"program": "apt-get", "argv_prefix": ["apt-get", "--simulate",
    "install"], "stdout_file": "apt-simulate.txt"}`` to distinguish several
    commands from the same program.  A record may instead carry a
    ``"sequence"`` list of result objects, replayed in order with the last
    repeating once exhausted -- apply queries dpkg before *and* after a
    step, so one static result would misread the second answer.  An
    unmapped argv raises CommandError.  Every call's ``env`` lands in
    ``seen_env`` so tests can assert what was sent.
    """

    def __init__(
        self,
        results: (
            dict[tuple[str, ...], CommandResult]
            | dict[tuple[str, ...], list[CommandResult]]
        ),
    ) -> None:
        self._remaining: dict[tuple[str, ...], list[CommandResult]] = {
            prefix: (list(value) if isinstance(value, list) else [value])
            for prefix, value in results.items()
        }
        self.seen_env: list[dict[str, str] | None] = []

    @classmethod
    def load(cls, commands_dir: Path) -> "ScriptedRunner":
        results: dict[tuple[str, ...], list[CommandResult]] = {}
        if commands_dir.is_dir():
            for path in sorted(commands_dir.glob("*.json")):
                if path.name == "statvfs.json":
                    continue
                try:
                    record = json.loads(path.read_text())
                except json.JSONDecodeError:
                    continue  # payload file (may be deliberately broken)
                if not isinstance(record, dict) or "program" not in record:
                    continue
                prefix = tuple(record.get("argv_prefix") or (record["program"],))
                replay = []
                for item in record.get("sequence") or [record]:
                    stdout = (
                        (path.parent / item["stdout_file"]).read_text()
                        if "stdout_file" in item
                        else item.get("stdout", "")
                    )
                    replay.append(
                        CommandResult(
                            argv=prefix,
                            returncode=item.get("returncode", 0),
                            stdout=stdout,
                            stderr=item.get("stderr", ""),
                        )
                    )
                results[prefix] = replay
        return cls(results)

    def run(
        self,
        argv: Sequence[str],
        *,
        timeout: float = 10.0,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        self.seen_env.append(dict(env) if env is not None else None)
        command = tuple(argv)
        for length in range(len(command), 0, -1):  # longest prefix wins
            candidate = command[:length]
            if candidate in self._remaining:
                results = self._remaining[candidate]
                if len(results) > 1:  # consume the sequence, then repeat last
                    return results.pop(0)
                return results[0]
        raise CommandError(
            f"no scripted result for '{' '.join(command[:3])}'"
        )


class FakeStatvfs:
    """Return a canned statvfs result regardless of the path probed."""

    def __init__(self, **values: int) -> None:
        self._values = SimpleNamespace(**{**STATVFS_DEFAULTS, **values})

    def __call__(self, path: Path) -> SimpleNamespace:
        return self._values

    @classmethod
    def load(cls, commands_dir: Path) -> "FakeStatvfs":
        record_path = commands_dir / "statvfs.json"
        record = json.loads(record_path.read_text()) if record_path.exists() else {}
        return cls(**record)
