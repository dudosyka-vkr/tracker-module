"""HTTP client wrapper for backend API calls."""

from __future__ import annotations

import logging
from collections.abc import Callable

import requests

logger = logging.getLogger(__name__)


def _file_names(files) -> list[str] | None:
    if not files:
        return None
    return [entry[0] for entry in files]


class ApiError(Exception):
    """Raised when the backend returns a non-2xx response."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(f"HTTP {status}: {message}")
        self.status = status
        self.message = message


class HttpClient:
    """Thin wrapper around requests.Session bound to a base URL and optional JWT.

    Set ``on_unauthorized`` to a callable that will be invoked whenever the
    server returns 401 (expired / missing token), before the ApiError is raised.
    """

    def __init__(self, base_url: str, token: str | None = None, timeout: int = 30) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self.on_unauthorized: Callable[[], None] | None = None
        self.set_token(token)

    def set_token(self, token: str | None) -> None:
        if token:
            self._session.headers["Authorization"] = f"Bearer {token}"
        else:
            self._session.headers.pop("Authorization", None)

    # -- public methods -------------------------------------------------------

    def get(self, path: str, params: list[tuple] | dict | None = None) -> dict:
        logger.info("GET %s params=%s", self._url(path), params)
        resp = self._session.get(self._url(path), params=params, timeout=self._timeout)
        return self._parse(resp)

    def get_bytes(self, path: str) -> bytes:
        logger.info("GET %s", self._url(path))
        resp = self._session.get(self._url(path), timeout=self._timeout)
        self._check(resp)
        logger.info("  -> %s (%d bytes)", resp.status_code, len(resp.content))
        return resp.content

    def post(
        self,
        path: str,
        json: dict | None = None,
        files=None,
        data: dict | None = None,
    ) -> dict:
        logger.info("POST %s body=%s data=%s files=%s", self._url(path), json, data, _file_names(files))
        resp = self._session.post(self._url(path), json=json, files=files, data=data, timeout=self._timeout)
        return self._parse(resp)

    def put(
        self,
        path: str,
        json: dict | None = None,
        files=None,
        data: dict | None = None,
    ) -> dict:
        logger.info("PUT %s body=%s data=%s files=%s", self._url(path), json, data, _file_names(files))
        resp = self._session.put(self._url(path), json=json, files=files, data=data, timeout=self._timeout)
        return self._parse(resp)

    def patch(
        self,
        path: str,
        json: dict | None = None,
        files=None,
        data: dict | None = None,
    ) -> dict:
        logger.info("PATCH %s body=%s data=%s files=%s", self._url(path), json, data, _file_names(files))
        resp = self._session.patch(self._url(path), json=json, files=files, data=data, timeout=self._timeout)
        return self._parse(resp)

    def delete(self, path: str) -> None:
        logger.info("DELETE %s", self._url(path))
        resp = self._session.delete(self._url(path), timeout=self._timeout)
        self._check(resp)

    # -- private helpers ------------------------------------------------------

    def _url(self, path: str) -> str:
        return self._base_url + path

    def _check(self, resp: requests.Response) -> None:
        if not resp.ok:
            try:
                msg = resp.json().get("message", resp.text)
            except Exception:
                msg = resp.text
            logger.info("  -> %s %s", resp.status_code, msg)
            if resp.status_code == 401 and self.on_unauthorized is not None:
                self.on_unauthorized()
            raise ApiError(resp.status_code, msg)

    def _parse(self, resp: requests.Response) -> dict:
        self._check(resp)
        if not resp.content:
            logger.info("  -> %s (empty body)", resp.status_code)
            return {}
        body = resp.json()
        logger.info("  -> %s %s", resp.status_code, body)
        return body
