"""
backend/session_auth.py

The logged-in user behind a session cookie. At login the session gets a
stamp derived from the password hash; a session whose stamp no longer
matches (the password was changed or the account reset since) is cleared.
Before v0.9.2 sessions stayed valid after a credential change.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Optional

from fastapi import HTTPException, Request
from sqlalchemy.orm import Session

from backend.models.user import User

STAMP_KEY = "cred"


def credential_stamp(user: User) -> str:
    return hashlib.sha256(f"{user.id}:{user.password_hash}".encode()).hexdigest()[:24]


def start_session(request: Request, user: User) -> None:
    request.session["user_id"] = user.id
    request.session[STAMP_KEY] = credential_stamp(user)


def session_user_id(request: Request, db: Session) -> Optional[int]:
    """The logged-in user's id, or None (a stale session is cleared)."""
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.get(User, user_id)
    stamp = request.session.get(STAMP_KEY) or ""
    if user is None or not hmac.compare_digest(stamp, credential_stamp(user)):
        request.session.clear()
        return None
    return user_id


def require_login(request: Request, db: Session, status: int = 401) -> int:
    user_id = session_user_id(request, db)
    if user_id is None:
        raise HTTPException(status_code=status, detail="Not authenticated")
    return user_id
