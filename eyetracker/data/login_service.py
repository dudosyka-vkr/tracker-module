"""Abstract login service and local implementation."""

from __future__ import annotations

import base64
import json
import secrets
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AuthResult:
    """Result of a successful login."""

    token: str
    username: str


class LoginService(ABC):
    """Abstract interface for authentication.

    Implementations may authenticate locally (LocalLoginService) or via remote API.
    """

    @abstractmethod
    def login(self, username: str, password: str) -> AuthResult:
        """Authenticate a user and return an AuthResult with a JWT token."""


class LocalLoginService(LoginService):
    """Local login service that always succeeds with a fake JWT."""

    def login(self, username: str, password: str) -> AuthResult:
        token = self._generate_fake_jwt(username)
        return AuthResult(token=token, username=username)

    @staticmethod
    def _generate_fake_jwt(username: str) -> str:
        header = base64.urlsafe_b64encode(
            json.dumps({"alg": "HS256", "typ": "JWT"}).encode()
        ).rstrip(b"=").decode()

        payload = base64.urlsafe_b64encode(
            json.dumps({
                "email": username,
                "role": "USER",
                "iat": int(time.time()),
                "exp": int(time.time()) + 3600,
            }).encode()
        ).rstrip(b"=").decode()

        signature = secrets.token_urlsafe(32)

        return f"{header}.{payload}.{signature}"
