"""
A size limit on every request body, checked before anything reads it:
FastAPI reads a body (and parses it) before any dependency, the login check
included, so the routes anyone can reach (login, Create account, the
account reset) took a body of any size. A body over its limit is answered
413: with a Content-Length over it before a byte is read, and sent in
chunks as soon as the bytes that came pass it.

The limit is MAX_BODY_BYTES; a route taking a file (main.py lists them)
takes that file's own limit, with FORM_ROOM for the form around it, and
still checks the file itself.
"""

from __future__ import annotations

from fastapi import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 5 * 1024 * 1024
# The multipart form around an uploaded file: its boundaries, headers and
# the other fields (the restore's password).
FORM_ROOM = 64 * 1024


def too_large(limit: int) -> str:
    return f"Request too large. Maximum size is {limit // (1024 * 1024)}MB."


class _TooLarge(HTTPException):
    """Raised from `receive`: FastAPI passes an HTTPException on while it
    reads a body, and the app answers it with its detail."""


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, file_limits: dict[str, int]):
        self.app = app
        # path: the file limit of a route taking a file
        self.limits = {path: max(MAX_BODY_BYTES, limit + FORM_ROOM) for path, limit in file_limits.items()}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.limits.get(scope["path"].rstrip("/"), MAX_BODY_BYTES)
        if _content_length(scope) > limit:
            await JSONResponse({"detail": too_large(limit)}, status_code=413)(scope, receive, send)
            return
        received = 0

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > limit:
                raise _TooLarge(status_code=413, detail=too_large(limit))
            return message

        await self.app(scope, counted, send)


def _content_length(scope: Scope) -> int:
    """The Content-Length header's value, 0 without one (a body in chunks)."""
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            return int(value) if value.isdigit() else 0
    return 0
