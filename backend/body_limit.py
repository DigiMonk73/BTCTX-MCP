"""
A size limit on every request body, checked before anything reads it:
FastAPI reads a body (and parses it) before any dependency, the login check
included, so the routes anyone can reach (login, Create account, the
account reset) took a body of any size. A body over its limit is answered
413: with a Content-Length over it before a byte is read, and sent in
chunks as soon as the bytes that came pass it, unless the answer is already
under way (_Counted says how each case ends).

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
BUSY = "BitcoinTX is busy: try again in a moment."
# The multipart form around an uploaded file: its boundaries, headers and
# the other fields (the restore's password).
FORM_ROOM = 64 * 1024
MAX_LENGTH_DIGITS = 18  # a Content-Length of more is over an exabyte


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
        if limit is None:
            await JSONResponse({"detail": BUSY}, status_code=503)(scope, receive, send)
            return
        if _content_length(scope) > limit:
            await JSONResponse({"detail": too_large(limit)}, status_code=413)(scope, receive, send)
            return
        await _Counted(limit, receive, send).run(self.app, scope)

    async def _limit(self, scope: Scope) -> int | None:
        """This request's limit; None when the database is too busy to say
        whether its session is open."""
        file_limit = self.file_limits.get(scope["path"].rstrip("/"))
        if file_limit is None:
            return MAX_BODY_BYTES
        session = self._session(scope)
        if session is None:
            return MAX_BODY_BYTES
        live = await to_thread.run_sync(_is_live, scope, session)
        if live is None:
            return None
        return file_limit if live else MAX_BODY_BYTES

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


class _Counted:
    """
    One request's body, counted as the app reads it, and how a body past
    the limit ends:

    - Before the answer has started, receive() refuses it (_TooLarge), and
      the 413 is this middleware's own: whatever the app sends from then on
      is dropped, and so is the error the refusal becomes on its way out,
      so the client gets one 413 and the log no error (#430). The app may
      answer the refusal itself (FastAPI's 413, the same words), or a file
      being sent may send its 200's start while the refusal unwinds it,
      which Starlette then turns into "response already started".
    - Once the answer has started, nothing can be refused any more: the
      rest of the body is read and thrown away (each chunk comes back
      empty), and the answer goes on. Starlette's FileResponse (from 1.8,
      under an ASGI spec below 2.4, as uvicorn's) reads receive() while it
      sends a file, to see the client leave, and so reads a body no route
      asked for: a GET for the page or a script with a body in chunks past
      the limit was refused in the middle of the file, cut off with an
      error in the log (#589's review).
    """

    def __init__(self, limit: int, receive: Receive, send: Send):
        self.limit = limit
        self._receive = receive
        self._send = send
        self.received = 0
        self.started = False
        self.refused: _TooLarge | None = None

    async def run(self, app: ASGIApp, scope: Scope) -> None:
        try:
            await app(scope, self.receive, self.send)
        except Exception as error:
            if self.refused is None or not _comes_from(error, self.refused):
                raise
        if self.refused is not None:
            await JSONResponse({"detail": self.refused.detail}, status_code=413)(scope, self._receive, self._send)

    async def receive(self) -> Message:
        message = await self._receive()
        self.received += len(message.get("body", b""))
        if self.received <= self.limit or message["type"] != "http.request":
            return message
        if self.started:
            return {**message, "body": b""}
        self.refused = self.refused or _TooLarge(status_code=413, detail=too_large(self.limit))
        raise self.refused

    async def send(self, message: Message) -> None:
        if self.refused is not None:
            return  # run() answers the 413
        self.started = self.started or message["type"] == "http.response.start"
        await self._send(message)


def _comes_from(error: BaseException | None, cause: BaseException) -> bool:
    """Whether `error` is `cause`, or was raised from it (`raise ... from`, as
    Starlette's "response already started" is). One merely raised while
    handling it is another failure: raised and logged, never folded into the
    413 (#589's re-check)."""
    seen = set()
    while error is not None and id(error) not in seen:
        if error is cause:
            return True
        seen.add(id(error))
        error = error.__cause__
    return False


def _is_live(scope: Scope, session: dict) -> bool | None:
    """Whether the session is still open, asked of the app's own database
    (get_db, or a test's override of it); None when it can't answer (a busy
    database), which the owner is told."""
    from backend.database import get_db
    from backend.session_auth import session_is_live

    sessions = scope["app"].dependency_overrides.get(get_db, get_db)()
    db = next(sessions)
    try:
        return session_is_live(session, db)
    except SQLAlchemyError:
        return None
    finally:
        sessions.close()


def _header(scope: Scope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return ""


def _content_length(scope: Scope) -> int:
    """
    The Content-Length header's value, 0 without one (a body in chunks; the
    bytes are counted as they come). Only ASCII digits are a length:
    str.isdigit() also takes '²', which int() refuses. One of more digits
    than any body has is past every limit, without asking int() for a number
    longer than it reads (4,300 digits).
    """
    length = _header(scope, b"content-length")
    if not (length.isascii() and length.isdigit()):
        return 0
    digits = length.lstrip("0") or "0"
    return int(digits) if len(digits) <= MAX_LENGTH_DIGITS else 10**MAX_LENGTH_DIGITS
