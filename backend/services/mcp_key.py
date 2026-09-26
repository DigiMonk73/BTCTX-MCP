"""
backend/services/mcp_key.py

The Mac app's AI assistant key: lets the MCP server on the same computer use
BitcoinTX without the user's password.

- Only in the Mac app: the launcher sets BTCTX_MCP_FILE (with BTCTX_DESKTOP).
  Anywhere else (Docker, StartOS) this is all off and the MCP server logs in
  with a username and password as before.
- The key is random (never the password). Only its SHA-256 is kept in the
  database (app_settings); the key itself is written to BTCTX_MCP_FILE
  (~/Library/Application Support/BitcoinTX/mcp.json, owner-only) with the
  URL, port and pid, where the MCP server finds it.
- It stays the same across restarts, so setup is done once. Resetting it
  (Settings) writes a new one: copies of the old one stop working at once,
  while the MCP server re-reads the file and carries on.
- It is accepted only from 127.0.0.1/::1, only while AI access is on, and
  only where the app accepts its API key (get_current_user) plus entry
  import. Backup/restore, CSV import and delete-all stay login-only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import tempfile
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from backend.services.desktop import desktop_info, is_desktop

logger = logging.getLogger(__name__)

HASH_KEY = "mcp_key_sha256"
ACCESS_KEY = "mcp_access"
LOCAL_HOSTS = {"127.0.0.1", "::1"}


def mcp_file() -> Optional[Path]:
    """Where the key file goes, or None when the feature is off."""
    path = os.environ.get("BTCTX_MCP_FILE")
    return Path(path) if (path and is_desktop()) else None


def enabled() -> bool:
    return mcp_file() is not None


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _get(db: Session, key: str) -> Optional[str]:
    from backend.models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: str) -> None:
    from backend.models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.flush()


def access_on(db: Session) -> bool:
    return _get(db, ACCESS_KEY) != "off"


def _read_file_token(path: Path) -> Optional[str]:
    try:
        token = json.loads(path.read_text()).get("token")
    except (OSError, ValueError, AttributeError):
        return None
    return token if isinstance(token, str) and len(token) >= 32 else None


def _write_file(path: Path, token: str) -> None:
    """Atomically write the key file, owner-only (0600) in an owner-only dir."""
    from backend.version import app_version

    info = desktop_info()
    data = {
        "url": info["url"],
        "port": info["port"],
        "pid": os.getpid(),
        "version": app_version(),
        "token": token,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".mcp-", suffix=".json")
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def sync(db: Session) -> None:
    """
    At startup and after a restore: keep the key the file already has (so
    nothing needs setting up again), or make one; record its hash; rewrite
    the file with this run's port and pid.
    """
    path = mcp_file()
    if path is None:
        return
    token = _read_file_token(path)
    if token is None:
        token = secrets.token_urlsafe(32)
        logger.info("AI assistant key created")
    if _get(db, HASH_KEY) != _hash(token):
        _set(db, HASH_KEY, _hash(token))
    db.commit()
    _write_file(path, token)


def rotate(db: Session) -> None:
    """A new key: the old one stops working immediately."""
    path = mcp_file()
    if path is None:
        raise RuntimeError("AI assistant keys exist only in the Mac app")
    token = secrets.token_urlsafe(32)
    _set(db, HASH_KEY, _hash(token))
    db.commit()
    _write_file(path, token)
    logger.info("AI assistant key reset")


def set_access(db: Session, on: bool) -> None:
    _set(db, ACCESS_KEY, "on" if on else "off")
    db.commit()
    logger.info("AI assistant access turned %s", "on" if on else "off")


class KeyRefused(Exception):
    """A key was presented but can't be used; the message says why."""


def bearer_token(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization[:7].lower() == "bearer ":
        return authorization[7:].strip() or None
    return None


def check_key(token: str, client_host: Optional[str], db: Session) -> None:
    """
    Accept or raise KeyRefused. Refusals are logged without the key.
    """
    if not enabled():
        raise KeyRefused("AI assistant keys aren't used on this server; log in instead.")
    if client_host not in LOCAL_HOSTS:
        logger.warning("AI assistant key refused: request from %s, not this computer", client_host)
        raise KeyRefused("The AI assistant key only works from this computer.")
    stored = _get(db, HASH_KEY)
    if not stored or not hmac.compare_digest(stored, _hash(token)):
        logger.warning("AI assistant key refused: not the current key")
        raise KeyRefused("AI assistant key not accepted (it may have been reset).")
    if not access_on(db):
        logger.info("AI assistant key refused: access is turned off")
        raise KeyRefused("AI assistant access is turned off in BitcoinTX Settings.")


def request_has_valid_key(request, db: Session) -> bool:
    """
    True if the request carries the current key under the rules above. A
    refusal's reason is kept on request.state for the 401 message.
    """
    token = bearer_token(request.headers.get("authorization"))
    if token is None:
        return False
    try:
        check_key(token, request.client.host if request.client else None, db)
        return True
    except KeyRefused as exc:
        request.state.mcp_key_refusal = str(exc)
        return False


def require_login_or_key(request, db: Session) -> None:
    """Session login or the AI assistant key (used by entry import)."""
    from fastapi import HTTPException

    if request.session.get("user_id") or request_has_valid_key(request, db):
        return
    detail = getattr(request.state, "mcp_key_refusal", None) or "Not authenticated"
    raise HTTPException(status_code=401, detail=detail)
