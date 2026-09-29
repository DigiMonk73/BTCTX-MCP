"""
Response headers that keep the browser from leaking or loading anything:
- Content-Security-Policy: the page loads scripts, styles, fonts, images and
  data only from BitcoinTX itself (prices and block height come through the
  backend), and can't be framed. Not in the Mac app, whose native bridge
  (pywebview) injects scripts; its page contains no outside URLs anyway
  (backend/tests/test_privacy.py).
- Referrer-Policy: no-referrer, X-Content-Type-Options: nosniff,
  X-Frame-Options: DENY.
- The session cookie gets Secure when the request came over HTTPS (StartOS
  serves the app through its HTTPS proxy, which sets X-Forwarded-Proto), so
  the browser never sends it over plain HTTP. Plain-HTTP installs (the Mac
  app on 127.0.0.1, Docker on a LAN) keep working.

CrossSiteGuardMiddleware refuses a change (POST, PUT, PATCH, DELETE...) that
a browser sent from a page other than BitcoinTX's own. The cookie's
SameSite=Lax stops other sites, but not another app on the same host (a
different port on the StartOS server or LAN box counts as the same site),
whose page could otherwise post a restore or an import with the owner's
cookie. The browser's Sec-Fetch-Site decides when it is sent (same-origin,
or none for a request the user made); otherwise the Origin header must name
this server (Host or X-Forwarded-Host, and https when the request came over
HTTPS). Requests with neither header are not from a web page (the AI
connector, the CLI, curl, tests) and carry no browser cookie to abuse.
"""

from __future__ import annotations

from typing import Iterable, Optional
from urllib.parse import urlsplit

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.services.desktop import is_desktop

CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",  # React style attributes
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])

SESSION_COOKIE = b"btc_session_id="


def _is_https(scope: Scope) -> bool:
    if scope.get("scheme") == "https":
        return True
    for name, value in scope.get("headers", []):
        if name == b"x-forwarded-proto":
            return value.split(b",")[0].strip().lower() == b"https"
    return False


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        https = _is_https(scope)
        csp = not is_desktop()

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = []
                for name, value in message.get("headers", []):
                    if https and name == b"set-cookie" and value.startswith(SESSION_COOKIE) \
                            and b"; secure" not in value.lower():
                        value += b"; Secure"
                    headers.append((name, value))
                present = {name.lower() for name, _ in headers}
                extra = [
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                ]
                if csp:
                    extra.append((b"content-security-policy", CSP.encode()))
                headers += [(n, v) for n, v in extra if n not in present]
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
SAME_ORIGIN_SITES = {"same-origin", "none"}
CROSS_SITE_REFUSED = "Refused: this request came from another site's page."
DEFAULT_PORTS = {"http": "80", "https": "443"}


def _header(scope: Scope, name: bytes) -> Optional[str]:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1").strip()
    return None


def _host_port(host: str, scheme: str) -> str:
    """host[:port] in lower case, without the scheme's default port."""
    host = host.strip().lower()
    default = DEFAULT_PORTS.get(scheme)
    if default and host.endswith(":" + default):
        host = host[: -len(default) - 1]
    return host


def _origin_is_this_server(origin: str, scope: Scope) -> bool:
    parts = urlsplit(origin)
    if parts.scheme not in DEFAULT_PORTS or not parts.netloc:
        return False  # "null" (sandboxed page, file://...) or garbage
    if _is_https(scope) and parts.scheme != "https":
        return False
    # A plain-HTTP request may still come from an https page (a TLS proxy
    # that doesn't say so), so then only host:port is compared.
    names = [_header(scope, b"host"), (_header(scope, b"x-forwarded-host") or "").split(",")[0]]
    wanted = _host_port(parts.netloc, parts.scheme)
    return any(name and _host_port(name, parts.scheme) == wanted for name in names)


class CrossSiteGuardMiddleware:
    def __init__(self, app: ASGIApp, trusted_origins: Iterable[str] = ()):
        self.app = app
        # CORS_ALLOW_ORIGINS: pages the operator allowed to use the API
        self.trusted = {o.rstrip("/").lower() for o in trusted_origins}

    def _refuse(self, scope: Scope) -> bool:
        site = _header(scope, b"sec-fetch-site")
        origin = _header(scope, b"origin")
        if origin is not None and origin.rstrip("/").lower() in self.trusted:
            return False
        if site is not None:
            return site.lower() not in SAME_ORIGIN_SITES
        return origin is not None and not _origin_is_this_server(origin, scope)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS and self._refuse(scope):
            response = JSONResponse({"detail": CROSS_SITE_REFUSED}, status_code=403)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
