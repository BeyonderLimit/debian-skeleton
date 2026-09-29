"""Session components and the desktop/window-manager compatibility model.

Xfce and LXDE are desktop environments whose window manager can be swapped
(openbox is the classic companion); labwc and openbox are complete sessions
on their own; "none" is headless.  UKUI ships ukui-window-manager as an
integral part of its session and was never verified to survive a swap, so
it is treated as non-replaceable.  The compatibility model encodes all of
that instead of two unrestricted menus (README).
"""

from __future__ import annotations

from debian_skeleton.models import Selection

DESKTOP_PACKAGES: dict[str, tuple[str, ...]] = {
    "none": (),
    "xfce": ("task-xfce-desktop",),
    "lxde": ("task-lxde-desktop",),
    # A Wayland compositor, packaged separately from the desktop tasks.
    "labwc": ("labwc",),
    # A standalone X11 window manager also needs a panel and something to
    # launch from it: the classic light trio.
    "openbox": ("openbox", "lxpanel", "xterm"),
    # Experimental: Debian ships UKUI pieces but no task or metapackage.
    "ukui": ("ukui-panel", "ukui-session-manager", "ukui-control-center"),
}

# Desktops whose window manager can be swapped for a standalone one.
WM_REPLACEABLE: frozenset[str] = frozenset({"xfce", "lxde"})
WINDOW_MANAGERS: tuple[str, ...] = ("openbox",)


def validate_selection(selection: Selection) -> tuple[bool, str]:
    """Check the desktop/window-manager combination; returns (ok, explanation)."""
    if selection.window_manager is None:
        return True, "ok"
    if selection.window_manager not in WINDOW_MANAGERS:
        return False, f"unknown window manager {selection.window_manager!r}"
    if selection.desktop not in WM_REPLACEABLE:
        return False, (
            f"a window manager cannot be selected for desktop "
            f"{selection.desktop!r}: labwc and openbox are sessions "
            "themselves, 'none' is headless, and UKUI keeps its own "
            "window manager"
        )
    return True, "ok"
