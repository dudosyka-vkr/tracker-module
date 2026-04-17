"""Abstract login service interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AuthResult:
    """Result of a successful login."""

    token: str
    username: str
    role: str | None = None


class LoginService(ABC):
    """Abstract interface for authentication.

    Implementations may authenticate locally (LocalLoginService) or via remote API.
    """

    @abstractmethod
    def login(self, username: str, password: str) -> AuthResult:
        """Authenticate a user and return an AuthResult with a JWT token."""

    @abstractmethod
    def register(self, username: str, password: str) -> AuthResult:
        """Register a new user and return an AuthResult with a JWT token."""
