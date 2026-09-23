"""
Thin async client for the BitcoinTX REST API.

Authenticates with the app's normal username/password login (session
cookie) — the import endpoints are session-only by design — and logs in
again transparently when the session expires.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx


class BtctxError(Exception):
    """An API error with a message suitable for showing to the model."""


class BtctxClient:
    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        verify: bool | str = True,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        self._username = username
        self._password = password
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            verify=verify,
            timeout=120.0,  # previews fetch historical prices
            transport=transport,
        )
        self._logged_in = False

    @classmethod
    def from_env(cls) -> "BtctxClient":
        username = os.environ.get("BTCTX_USERNAME")
        password = os.environ.get("BTCTX_PASSWORD")
        if not username or not password:
            raise SystemExit("Set BTCTX_USERNAME and BTCTX_PASSWORD (your BitcoinTX login).")

        verify: bool | str = True
        if os.environ.get("BTCTX_CA_BUNDLE"):
            verify = os.environ["BTCTX_CA_BUNDLE"]
        elif os.environ.get("BTCTX_VERIFY_TLS", "true").lower() in ("0", "false", "no"):
            verify = False

        return cls(
            base_url=os.environ.get("BTCTX_URL", "http://localhost:80"),
            username=username,
            password=password,
            verify=verify,
        )

    async def _login(self) -> None:
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
            r = await self._http.request(method, path, **kwargs)
            if r.status_code == 401:
                await self._login()
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
