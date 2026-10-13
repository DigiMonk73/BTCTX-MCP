"""
The logged-in user behind a session cookie, and the sessions that are open.

Each login opens a session with a random id. The cookie carries the id, and
the server keeps the hashes of the open sessions' ids in app_settings (the
newest MAX_OPEN_SESSIONS). Logging out removes the id, so that cookie, and
any copy of it, stops working at once, while the owner's other browsers stay
logged in. The session also carries a stamp derived from the password hash.
A password change or account reset empties the list and changes the stamp,
so every session ends. A session that isn't open, or whose stamp no longer
matches, is cleared and counts as logged out (so does a cookie made before
sessions had ids).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
from collections.abc import Callable

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.app_setting import AppSetting
from backend.models.user import User

STAMP_KEY = "cred"
SESSION_ID_KEY = "sid"
OPEN_SESSIONS = "open_sessions"  # app_settings: JSON list of id hashes, oldest first
# One owner's browsers and devices, with room for logins never logged out
# (a closed window, the Mac app between launches); the list is read on
# every request, so it stays small.
MAX_OPEN_SESSIONS = 20

# FastAPI runs the routes in worker threads, and the app runs in one
# process: one change to the list at a time, each read and written whole.
_lock = threading.Lock()


def credential_stamp(user: User) -> str:
    return hashlib.sha256(f"{user.id}:{user.password_hash}".encode()).hexdigest()[:24]


def start_session(request: Request, user: User, db: Session) -> None:
    """Log this browser in as `user` with a new session id; its previous
    session, if it had one, ends."""
    session_id = secrets.token_urlsafe(32)
    cookie = {"user_id": user.id, STAMP_KEY: credential_stamp(user), SESSION_ID_KEY: session_id}
    previous = _id_hash(request.session.get(SESSION_ID_KEY))
    _change_open_sessions(db, lambda hashes: [h for h in hashes if h != previous] + [_id_hash(session_id)])
    request.session.clear()
    request.session.update(cookie)


def end_session(request: Request, db: Session) -> None:
    """Log this browser out: its session stops working, a copy of the
    cookie included."""
    ended = _id_hash(request.session.get(SESSION_ID_KEY))
    if ended:
        _change_open_sessions(db, lambda hashes: [h for h in hashes if h != ended])
    request.session.clear()


def end_all_sessions(db: Session) -> None:
    """Every browser logs in again (a password change, an account reset).
    Commits, with anything else pending in `db`."""
    _change_open_sessions(db, lambda _hashes: [])


def open_sessions(db: Session) -> list[str]:
    """The open sessions' id hashes, oldest first (none when unreadable);
    a restore puts them back with carry_over."""
    raw = db.execute(select(AppSetting.value).where(AppSetting.key == OPEN_SESSIONS)).scalar()
    try:
        hashes = json.loads(raw) if raw else []
    except ValueError:
        return []
    return [h for h in hashes if isinstance(h, str)] if isinstance(hashes, list) else []


def carry_over(db: Session, before: list[str]) -> None:
    """After a restore, the sessions open before it stay open, and only
    those: the backup's list never brings back a session that ended."""
    _change_open_sessions(db, lambda _hashes: before)


def session_user_id(request: Request, db: Session) -> int | None:
    """The logged-in user's id, or None (an ended or stale session is cleared)."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    if user is None or not _stamp_matches(request, user) or not _is_open(request, db):
        request.session.clear()
        return None
    return user_id


def require_login(request: Request, db: Session, status: int = 401) -> int:
    user_id = session_user_id(request, db)
    if user_id is None:
        raise HTTPException(status_code=status, detail="Not authenticated")
    return user_id


def _stamp_matches(request: Request, user: User) -> bool:
    stamp = request.session.get(STAMP_KEY)
    return isinstance(stamp, str) and hmac.compare_digest(stamp, credential_stamp(user))


def _is_open(request: Request, db: Session) -> bool:
    session_hash = _id_hash(request.session.get(SESSION_ID_KEY))
    return session_hash is not None and session_hash in open_sessions(db)


def _id_hash(session_id: object) -> str | None:
    """Only the ids' hashes are stored, so the database (or a backup of it)
    holds nothing a cookie could be made from."""
    if not isinstance(session_id, str) or not session_id:
        return None
    return hashlib.sha256(session_id.encode()).hexdigest()


def _change_open_sessions(db: Session, change: Callable[[list[str]], list[str]]) -> None:
    """Replace the open sessions with change(them), keeping the newest
    MAX_OPEN_SESSIONS; read, written and committed under the lock."""
    with _lock:
        value = json.dumps(change(open_sessions(db))[-MAX_OPEN_SESSIONS:])
        row = db.get(AppSetting, OPEN_SESSIONS)
        if row is None:
            db.add(AppSetting(key=OPEN_SESSIONS, value=value))
        else:
            row.value = value
        db.commit()
