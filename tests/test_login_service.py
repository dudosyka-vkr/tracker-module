"""Tests for login service."""

import base64
import json

from eyetracker.data.login import LocalLoginService


def test_login_returns_auth_result():
    svc = LocalLoginService()
    result = svc.login("user@test.com", "password123")
    assert result.username == "user@test.com"
    assert isinstance(result.token, str)


def test_token_has_three_parts():
    svc = LocalLoginService()
    result = svc.login("user@test.com", "pass")
    parts = result.token.split(".")
    assert len(parts) == 3


def test_token_payload_contains_username():
    svc = LocalLoginService()
    result = svc.login("admin@example.com", "pass")
    payload_part = result.token.split(".")[1]
    # Add padding for base64 decode
    padding = 4 - len(payload_part) % 4
    if padding != 4:
        payload_part += "=" * padding
    payload = json.loads(base64.urlsafe_b64decode(payload_part))
    assert payload["email"] == "admin@example.com"
    assert payload["role"] == "USER"
    assert "exp" in payload
