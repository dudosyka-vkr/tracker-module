"""Tests for create_test_form validation."""

from eyetracker.create_test_form import validate_form


def test_validate_empty_name():
    errors = validate_form("", "/cover.png", ["/img.png"])
    assert "name" in errors


def test_validate_whitespace_name():
    errors = validate_form("   ", "/cover.png", ["/img.png"])
    assert "name" in errors


def test_validate_no_cover():
    errors = validate_form("Test", None, ["/img.png"])
    assert "cover" in errors


def test_validate_no_images():
    errors = validate_form("Test", "/cover.png", [])
    assert "images" in errors


def test_validate_all_valid():
    errors = validate_form("Test", "/cover.png", ["/img.png"])
    assert errors == {}


def test_validate_multiple_errors():
    errors = validate_form("", None, [])
    assert "name" in errors
    assert "cover" in errors
    assert "images" in errors
    assert len(errors) == 3
