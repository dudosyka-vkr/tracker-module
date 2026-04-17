"""Remote HTTP implementation of LoginService."""

from __future__ import annotations

from eyetracker.data.http_client import HttpClient
from eyetracker.data.login.service import AuthResult, LoginService


class ApiLoginService(LoginService):
    """Authenticates against the backend REST API."""

    def __init__(self, client: HttpClient) -> None:
        self._client = client

    def login(self, username: str, password: str) -> AuthResult:
        resp = self._client.post(
            "/auth/login",
            json={"login": username, "password": password},
        )
        result = AuthResult(token=resp["token"], username=username)
        self._client.set_token(result.token)
        result.role = self._fetch_role()
        return result

    def register(self, username: str, password: str) -> AuthResult:
        resp = self._client.post(
            "/auth/register",
            json={"login": username, "password": password},
        )
        result = AuthResult(token=resp["token"], username=username)
        self._client.set_token(result.token)
        result.role = self._fetch_role()
        return result

    def _fetch_role(self) -> str | None:
        try:
            resp = self._client.get("/auth/me/role")
            return resp.get("role")
        except Exception:
            return None
