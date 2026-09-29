"""Size and intended-use package sets.

Pure data: tuning a profile never touches planner logic.  Sets are
deliberately small and conservative — the plan stage resolves them against
real APT state, so an overgrown catalog hides what actually happens.
"""

from __future__ import annotations

_STANDARD = ("bash-completion", "curl", "less", "rsync", "xdg-utils")

SIZE_PACKAGES: dict[str, tuple[str, ...]] = {
    "minimal": (),
    "laptop": ("xdg-utils",),
    "standard": _STANDARD,
    "full": _STANDARD + ("htop", "unzip", "vim", "wget", "zip"),
}

PURPOSE_PACKAGES: dict[str, tuple[str, ...]] = {
    "daily": (),
    "development": ("build-essential", "git", "python3-pip", "python3-venv"),
    # Deliberately empty: Debian main carries no LLM runtime, and the spec
    # forbids silently pulling an LLM, voice stack, or model files.  The
    # planner states this explicitly instead of installing anything.
    "ai-assistant": (),
    "custom": (),
}
