"""
Thin async client for the BitcoinTX REST API.

Two ways in:
- The Mac app on the same computer: no settings needed. The app writes
  ~/Library/Application Support/BitcoinTX/mcp.json (owner-only) with its URL
  and an AI assistant key; the client reads it, sends the key as a bearer
  token, and reads it again if the key was reset or the app restarted.
- A server install (StartOS, Docker): BTCTX_URL, BTCTX_USERNAME and
  BTCTX_PASSWORD; the client logs in (session cookie) and logs in again
  when the session expires.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import httpx


class BtctxError(Exception):
    """An API error with a message suitable for showing to the model."""


def normalize_base_url(url: str) -> str:
    """
    The server root. Also accepts the API address StartOS lists under
    Interfaces (https://….local/api), since every request path starts with /api.
    """
    url = url.strip().rstrip("/")
    if url.endswith("/api"):
        url = url[: -len("/api")]
    return url


def default_key_file() -> Path:
    if os.environ.get("BTCTX_MCP_FILE"):
        return Path(os.environ["BTCTX_MCP_FILE"]).expanduser()
    return Path.home() / "Library" / "Application Support" / "BitcoinTX" / "mcp.json"


def _pid_alive(pid: Any) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == "win32":
        return True  # can't check cheaply; the health check decides
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class BtctxClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        verify: bool | str = True,
        transport: Optional[httpx.AsyncBaseTransport] = None,
        key_file: Optional[Path] = None,
    ):
        self._username = username
        self._password = password
        self._key_file = key_file
        self._configured_url = normalize_base_url(base_url) if base_url else None
        self._http = httpx.AsyncClient(
            base_url=self._configured_url or "http://127.0.0.1",
            verify=verify,
            timeout=120.0,  # previews fetch historical prices
            transport=transport,
        )
        self._logged_in = False

    @property
    def uses_key_file(self) -> bool:
        return self._key_file is not None

    @classmethod
    def from_env(cls) -> "BtctxClient":
        verify: bool | str = True
        if os.environ.get("BTCTX_CA_BUNDLE"):
            verify = os.environ["BTCTX_CA_BUNDLE"]
        elif os.environ.get("BTCTX_VERIFY_TLS", "true").lower() in ("0", "false", "no"):
            verify = False

        username = os.environ.get("BTCTX_USERNAME")
        password = os.environ.get("BTCTX_PASSWORD")
        if username and password:
            return cls(
                base_url=os.environ.get("BTCTX_URL", "http://localhost:80"),
                username=username,
                password=password,
                verify=verify,
            )
        # No login configured: the Mac app's key file (found at first use).
        return cls(base_url=os.environ.get("BTCTX_URL"), verify=verify, key_file=default_key_file())

    # -- the Mac app's key file ------------------------------------------------
    async def _answers(self, url: str) -> bool:
        try:
            r = await self._http.get(f"{url}/api/health", timeout=3.0)
        except httpx.HTTPError:
            return False
        return r.status_code in (200, 503)

    async def _use_key_file(self) -> None:
        """Point the client at the running Mac app, or explain what's missing."""
        path = self._key_file
        looked = [
            "BTCTX_USERNAME / BTCTX_PASSWORD: not set (only needed for a server install)",
        ]
        try:
            data = json.loads(path.read_text())
        except FileNotFoundError:
            looked.append(f"{path}: not found (the BitcoinTX Mac app writes it when it starts)")
            raise BtctxError(self._not_found(looked))
        except (OSError, ValueError) as exc:
            looked.append(f"{path}: unreadable ({exc})")
            raise BtctxError(self._not_found(looked))

        token, url, pid = data.get("token"), data.get("url"), data.get("pid")
        if not token or not url:
            looked.append(f"{path}: incomplete (no key or URL); reopen BitcoinTX")
            raise BtctxError(self._not_found(looked))
        if not _pid_alive(pid):
            looked.append(f"{path}: written by BitcoinTX (pid {pid}), which is no longer running")
            raise BtctxError(self._not_found(looked))
        url = normalize_base_url(url)
        if self._configured_url and self._configured_url != url and await self._answers(self._configured_url):
            url = self._configured_url
        if not await self._answers(url):
            looked.append(f"{path}: BitcoinTX at {url} doesn't answer")
            raise BtctxError(self._not_found(looked))
        self._http.base_url = url
        self._http.headers["Authorization"] = f"Bearer {token}"
        self._logged_in = True

    @staticmethod
    def _not_found(looked: list[str]) -> str:
        return (
            "Cannot reach BitcoinTX. Open the BitcoinTX app and try again. Looked at:\n- "
            + "\n- ".join(looked)
        )

    # -- username/password login ------------------------------------------------
    async def _login(self) -> None:
        if self.uses_key_file:
            await self._use_key_file()
            return
        try:
            r = await self._http.post(
                "/api/login", json={"username": self._username, "password": self._password}
            )
        except httpx.HTTPError as exc:
            raise BtctxError(f"Cannot reach BitcoinTX at {self._http.base_url}: {exc}") from exc
        if r.status_code != 200:
            raise BtctxError("BitcoinTX login failed — check BTCTX_USERNAME / BTCTX_PASSWORD.")
        self._logged_in = True

    async def request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._logged_in:
            await self._login()
        try:
            try:
                r = await self._http.request(method, path, **kwargs)
            except httpx.ConnectError:
                if not self.uses_key_file:
                    raise
                # The app restarted (maybe elsewhere): read the file again.
                await self._login()
                r = await self._http.request(method, path, **kwargs)
            if r.status_code == 401:
                await self._login()  # session expired, or the key was reset
                r = await self._http.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise BtctxError(f"Request to BitcoinTX failed: {exc}") from exc

        if r.is_error:
            try:
                detail = r.json().get("detail", r.text)
            except ValueError:
                detail = r.text
            if r.status_code == 404 and path.startswith("/api/import/entries"):
                detail = (
                    "This BitcoinTX server has no /api/import/entries endpoint — "
                    "upgrade it to a version that includes the MCP import API."
                )
            raise BtctxError(f"BitcoinTX returned {r.status_code}: {detail}")
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, json: Any) -> Any:
        return await self.request("POST", path, json=json)

    async def put(self, path: str, json: Any) -> Any:
        return await self.request("PUT", path, json=json)

    async def delete(self, path: str) -> Any:
        return await self.request("DELETE", path)

    async def aclose(self) -> None:
        await self._http.aclose()
