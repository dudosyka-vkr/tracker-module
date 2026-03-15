"""Time formatting utilities."""

from __future__ import annotations

from datetime import datetime, timezone


def format_datetime(iso_str: str) -> str:
    """Format ISO 8601 string to 'DD.MM.YYYY HH:MM'."""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, OSError):
        return iso_str
