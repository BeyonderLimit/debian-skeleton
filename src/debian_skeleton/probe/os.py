"""os-release probe.

Module-name note: this file is deliberately named ``os.py`` after the README
structure.  Python 3 absolute imports keep the stdlib ``os`` module
importable everywhere; to keep that true, never bind this module under the
bare name ``os`` — import members explicitly (``from .os import probe_os``),
and never ``from . import os`` in ``probe/__init__.py``.
"""

from __future__ import annotations

from debian_skeleton.models import OsInfo
from debian_skeleton.probe.context import ProbeContext

_CANDIDATE_PATHS = ("etc/os-release", "usr/lib/os-release")


def parse_os_release(text: str) -> dict[str, str]:
    """Parse os-release(5) content: KEY=value lines, optional quotes, comments."""
    fields: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key.strip()] = value
    return fields


def probe_os(ctx: ProbeContext) -> OsInfo:
    """Identify the OS from etc/os-release, falling back to usr/lib/os-release."""
    text: str | None = None
    source_path: str | None = None
    for rel in _CANDIDATE_PATHS:
        text = ctx.read_optional_text(rel)
        if text is not None:
            source_path = "/" + rel
            break
    if text is None:
        ctx.warn(
            "etc/os-release",
            "no os-release found (also tried usr/lib/os-release)",
        )
        return OsInfo(
            id=None,
            version_id=None,
            version_codename=None,
            pretty_name=None,
            source_path=None,
        )
    fields = parse_os_release(text)
    return OsInfo(
        id=fields.get("ID"),
        version_id=fields.get("VERSION_ID"),
        version_codename=fields.get("VERSION_CODENAME"),
        pretty_name=fields.get("PRETTY_NAME"),
        source_path=source_path,
    )
