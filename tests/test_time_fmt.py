"""Tests for time formatting."""

from eyetracker.core.time_fmt import format_datetime


def test_format_utc_datetime():
    result = format_datetime("2025-01-15T14:30:00+00:00")
    assert "15.01.2025" in result
    assert ":" in result


def test_format_naive_datetime():
    result = format_datetime("2025-06-01T09:15:00")
    assert result == "01.06.2025 09:15"


def test_format_invalid_returns_original():
    assert format_datetime("not-a-date") == "not-a-date"


def test_format_with_z_suffix():
    result = format_datetime("2025-03-10T12:00:00Z")
    assert "10.03.2025" in result
