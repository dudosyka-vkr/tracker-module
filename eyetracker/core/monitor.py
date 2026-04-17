"""Monitor resolution utilities for multi-display support."""

from __future__ import annotations

from PyQt6.QtGui import QScreen
from PyQt6.QtWidgets import QApplication


def get_available_screens() -> list[QScreen]:
    """Return all screens currently connected."""
    return QApplication.screens()


def resolve_screen(display_name: str | None) -> QScreen:
    """Find a QScreen by name, falling back to the primary screen.

    Args:
        display_name: Value from Settings.tracking_display_name.
            None means "use primary monitor".

    Returns:
        The matched QScreen, or primary if not found.
    """
    primary = QApplication.primaryScreen()
    if display_name is None:
        return primary

    for screen in QApplication.screens():
        if screen.name() == display_name:
            return screen

    return primary


def format_screen_label(screen: QScreen) -> str:
    """Format a human-readable label for a screen.

    Example: 'Built-in Retina Display — 2560x1600 @ (0, 0)'
    """
    geo = screen.geometry()
    return (
        f"{screen.name()} — "
        f"{geo.width()}x{geo.height()} @ ({geo.x()}, {geo.y()})"
    )
