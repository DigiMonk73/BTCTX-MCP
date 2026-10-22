"""
An error nobody expected, said and logged without its own text: that text
can hold SQL with its parameters (a transaction's date) or a server path,
and transaction dates stay out of the normal log (AGENTS.md "Security
rules"; #204, #422, #430).

- log_unexpected: the error's type at ERROR, its trace only at DEBUG,
  where whole rows already are, in the caller's log.
- UnexpectedErrorMiddleware: an error no route handled answers one fixed
  sentence (500) and is logged so. Starlette's own handler answers too,
  but raises the error again for the server, which then logs the whole
  trace at ERROR ("Exception in ASGI application"). A save a restore's
  swap refused (database.was_replaced) says so instead (503), and so does
  one that waited past SQLite's 5 s for the write lock (database.is_busy:
  an import held it), in the imports' words (503, #478).
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.database import is_busy, was_replaced

logger = logging.getLogger(__name__)

UNEXPECTED = "Something unexpected went wrong. BitcoinTX's log says what."
REPLACED = "A restore replaced the database while this was being saved, so it wasn't saved. Check, then try again."
BUSY = "BitcoinTX was busy saving something else, and nothing was changed. Try again."


def log_unexpected(what: str, error: Exception, log: logging.Logger = logger, then: str = "") -> None:
    """`what` failed with `error`: its type in the log at ERROR (with what
    follows from it, `then`), its trace at DEBUG."""
    log.error("%s failed: %s%s", what, type(error).__name__, then)
    log.debug("%s failed", what, exc_info=error)


class UnexpectedErrorMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def send_tracked(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, send_tracked)
        except Exception as error:
            # The path quoted (as uvicorn's access log does: a %0A is no new line), without its query
            what = f"{scope['method']} {quote(scope['path'])}"
            if was_replaced(error):
                logger.warning("%s not saved: a restore replaced the database meanwhile", what)
                answer = JSONResponse({"detail": REPLACED}, status_code=503)
            elif is_busy(error):
                logger.warning("%s: the database was busy, nothing changed", what)
                answer = JSONResponse({"detail": BUSY}, status_code=503)
            else:
                log_unexpected(what, error)
                answer = JSONResponse({"detail": UNEXPECTED}, status_code=500)
            if not started:  # else the answer is under way: nothing more can be sent
                await answer(scope, receive, send)
