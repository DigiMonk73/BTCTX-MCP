"""
A size limit on every request body, checked before anything reads it:
FastAPI reads a body (and parses it) before any dependency, the login check
included, so the routes anyone can reach (login, Create account, the
account reset) took a body of any size. A body over its limit is answered
413: with a Content-Length over it before a byte is read, and sent in
chunks as soon as the bytes that came pass it.

The limit is MAX_BODY_BYTES. A route taking a file (main.py lists them)
takes that file's own limit, with FORM_ROOM for the form around it, and
still checks the file itself; the larger allowance is for a logged-in
owner's file, so only a request whose session cookie is validly signed and
unexpired (as SessionMiddleware writes it) and names a session still open
(session_auth.session_is_live, as the route's own login check asks) gets it.
"""

from __future__ import annotations

import binascii
import json
from base64 import b64decode

import itsdangerous
from anyio import to_thread
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import cookie_parser
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
    def __init__(self, app: ASGIApp, file_limits: dict[str, int], secret_key: str, session_cookie: str,
                 max_age: int):
        self.app = app
        # path: the file limit of a route taking a file
        self.file_limits = {path: max(MAX_BODY_BYTES, limit + FORM_ROOM) for path, limit in file_limits.items()}
        self.signer = itsdangerous.TimestampSigner(str(secret_key))
        self.session_cookie = session_cookie
        self.max_age = max_age

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = await self._limit(scope)
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

    async def _limit(self, scope: Scope) -> int:
        file_limit = self.file_limits.get(scope["path"].rstrip("/"))
        if file_limit is None:
            return MAX_BODY_BYTES
        session = self._session(scope)
        if session is None or not await to_thread.run_sync(_is_live, scope, session):
            return MAX_BODY_BYTES
        return file_limit

    def _session(self, scope: Scope) -> dict | None:
        """The session cookie's contents if it is the app's, unexpired, with a
        user_id (as SessionMiddleware reads it)."""
        cookie = cookie_parser(_header(scope, b"cookie")).get(self.session_cookie)
        if not cookie:
            return None
        try:
            data = self.signer.unsign(cookie.encode(), max_age=self.max_age)
            session = json.loads(b64decode(data))
        except (itsdangerous.BadSignature, binascii.Error, ValueError):
            return None
        return session if isinstance(session, dict) and session.get("user_id") else None


def _is_live(scope: Scope, session: dict) -> bool:
    """Whether the session is still open, asked of the app's own database
    (get_db, or a test's override of it). A busy database counts as no: the
    owner is told the file is too large, and can try again."""
    from backend.database import get_db
    from backend.session_auth import session_is_live

    sessions = scope["app"].dependency_overrides.get(get_db, get_db)()
    db = next(sessions)
    try:
        return session_is_live(session, db)
    except SQLAlchemyError:
        return False
    finally:
        sessions.close()


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return ""


def _content_length(scope: Scope) -> int:
    """The Content-Length header's value, 0 without one (a body in chunks)."""
    length = _header(scope, b"content-length")
    return int(length) if length.isdigit() else 0
