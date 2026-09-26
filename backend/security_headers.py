"""
backend/security_headers.py

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
"""

from __future__ import annotations

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
