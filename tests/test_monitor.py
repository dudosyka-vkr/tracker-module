"""Tests for eyetracker.monitor."""

from unittest.mock import MagicMock, patch

from eyetracker.core.monitor import format_screen_label, resolve_screen


def _make_screen(name: str, x: int = 0, y: int = 0, w: int = 1920, h: int = 1080) -> MagicMock:
    screen = MagicMock()
    screen.name.return_value = name
    geo = MagicMock()
    geo.x.return_value = x
    geo.y.return_value = y
    geo.width.return_value = w
    geo.height.return_value = h
    screen.geometry.return_value = geo
    return screen


@patch("eyetracker.core.monitor.QApplication")
def test_resolve_screen_none_returns_primary(mock_app):
    primary = _make_screen("Primary")
    mock_app.primaryScreen.return_value = primary
    assert resolve_screen(None) is primary


@patch("eyetracker.core.monitor.QApplication")
def test_resolve_screen_unknown_returns_primary(mock_app):
    primary = _make_screen("Primary")
    mock_app.primaryScreen.return_value = primary
    mock_app.screens.return_value = [primary]
    assert resolve_screen("NonExistent") is primary


@patch("eyetracker.core.monitor.QApplication")
def test_resolve_screen_found(mock_app):
    primary = _make_screen("Primary")
    external = _make_screen("DELL U2720Q")
    mock_app.primaryScreen.return_value = primary
    mock_app.screens.return_value = [primary, external]
    assert resolve_screen("DELL U2720Q") is external


def test_format_screen_label():
    screen = _make_screen("Built-in Display", x=0, y=0, w=2560, h=1600)
    label = format_screen_label(screen)
    assert "Built-in Display" in label
    assert "2560x1600" in label
    assert "(0, 0)" in label
