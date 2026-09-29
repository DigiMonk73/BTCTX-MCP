"""
backend/services/ai_key.py

The AI key: lets an AI assistant's MCP connector use BitcoinTX without the
owner's password, on every edition. It can read the ledger, add, change or
delete single entries, recalculate and make a backup copy; it can't log in,
change the password, restore, import files or delete everything.

- Two ways of handing it over (mode()):
  - "mac": the Mac app's launcher sets BTCTX_MCP_FILE (with BTCTX_DESKTOP).
    BitcoinTX writes the key to that owner-only file (mcp.json, with the URL,
    port and pid), where the connector on the same Mac finds it. The key
    stays the same across restarts; "Reset key" writes a new one. Accepted
    only from 127.0.0.1/::1.
  - "server" (Docker, StartOS, anything else): the owner creates the key in
    Settings and pastes it into the AI app; BitcoinTX shows it once. "New
    key" replaces it, "Revoke" deletes it.
- Only its SHA-256 is stored, in app_settings (the names `mcp_key_sha256` and
  `mcp_access` are kept from v1.0.2 so Mac installs keep their key and
  switch). One key at a time: a new one stops the old one at once.
- Accepted only while AI access is on (off until the owner turns it on in
  Settings), and only on the routes in AI_KEY_ROUTES: what the MCP tools use.
  Anything else answers 403, so a route added later is closed to the key
  until someone lists it here on purpose. The login-only routes also check
  for a session themselves.
- The key is never logged, never returned except once at creation, and a
  restore keeps the current key and switch (see carry_over).
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
from starlette.routing import compile_path

from backend.services.desktop import desktop_info, is_desktop

logger = logging.getLogger(__name__)

HASH_KEY = "mcp_key_sha256"
ACCESS_KEY = "mcp_access"
LOCAL_HOSTS = {"127.0.0.1", "::1"}
PREFIX = "btctx_ak_"

NOT_ALLOWED = "The AI key can't do this. Log in to BitcoinTX to do it."
TURNED_OFF = "AI access is turned off in BitcoinTX Settings."

# (method, path, the MCP tool that needs it). {name:int} matches digits only,
# so /api/transactions/delete_all is never "a transaction".
# /api/health needs no login at all.
AI_KEY_ROUTES = (
    ("GET", "/api/transactions", "list_transactions"),
    ("GET", "/api/transactions/{transaction_id:int}", "update_transaction, delete_transaction"),
    ("PUT", "/api/transactions/{transaction_id:int}", "update_transaction"),
    ("DELETE", "/api/transactions/{transaction_id:int}", "delete_transaction"),
    ("POST", "/api/transactions/recalculate", "recalculate_ledger"),
    ("POST", "/api/import/entries/preview", "preview_transactions"),
    ("POST", "/api/import/entries/execute", "add_transactions"),
    ("GET", "/api/calculations/accounts/balances", "get_portfolio"),
    ("GET", "/api/calculations/average-cost-basis", "get_portfolio"),
    ("GET", "/api/bitcoin/price", "get_portfolio, get_btc_price"),
    ("GET", "/api/bitcoin/price/history", "get_btc_price"),
    ("GET", "/api/settings/tax-timezone", "get_portfolio, list_transactions, update_transaction"),
    ("GET", "/api/review", "review_ledger"),
    ("POST", "/api/backup/ai-copy", "backup_ledger"),
)
_ALLOWED = [(method, compile_path(path)[0]) for method, path, _ in AI_KEY_ROUTES]


def key_may_use(method: str, path: str) -> bool:
    """Is this request (method, URL path) one the AI key may make?"""
    path = path.rstrip("/") or "/"
    return any(m == method and regex.match(path) for m, regex in _ALLOWED)


# ---------------------------------------------------------------------------
# Mode and storage
# ---------------------------------------------------------------------------
def key_file() -> Optional[Path]:
    """The Mac app's key file, or None everywhere else."""
    path = os.environ.get("BTCTX_MCP_FILE")
    return Path(path) if (path and is_desktop()) else None


def mode() -> str:
    return "mac" if key_file() is not None else "server"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def _get(db: Session, key: str) -> Optional[str]:
    from backend.models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    return row.value if row else None


def _set(db: Session, key: str, value: Optional[str]) -> None:
    """Store a setting; None deletes it."""
    from backend.models.app_setting import AppSetting

    row = db.get(AppSetting, key)
    if value is None:
        if row:
            db.delete(row)
    elif row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.flush()


def access_on(db: Session) -> bool:
    """Off until the owner turns it on in Settings (new installs and upgrades)."""
    return _get(db, ACCESS_KEY) == "on"


def has_key(db: Session) -> bool:
    return bool(_get(db, HASH_KEY))


def set_access(db: Session, on: bool) -> None:
    _set(db, ACCESS_KEY, "on" if on else "off")
    db.commit()
    logger.info("AI access turned %s", "on" if on else "off")


# ---------------------------------------------------------------------------
# Server mode: the owner creates, replaces and revokes the key in Settings
# ---------------------------------------------------------------------------
def create_key(db: Session) -> str:
    """A new key (replacing any old one); returned once, never stored."""
    token = _new_token()
    _set(db, HASH_KEY, _hash(token))
    db.commit()
    logger.info("AI key created")
    return token


def revoke(db: Session) -> None:
    _set(db, HASH_KEY, None)
    db.commit()
    logger.info("AI key revoked")


# ---------------------------------------------------------------------------
# Mac mode: the key lives in the owner-only key file
# ---------------------------------------------------------------------------
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
    Mac app, at startup and after a restore: keep the key the file already
    has (so nothing needs setting up again), or make one; record its hash;
    rewrite the file with this run's port and pid.
    """
    path = key_file()
    if path is None:
        return
    token = _read_file_token(path)
    if token is None:
        token = _new_token()
        logger.info("AI key created")
    if _get(db, HASH_KEY) != _hash(token):
        _set(db, HASH_KEY, _hash(token))
    db.commit()
    _write_file(path, token)


def rotate(db: Session) -> None:
    """Mac app: a new key in the file; the old one stops working at once."""
    path = key_file()
    if path is None:
        raise RuntimeError("The key file exists only in the Mac app")
    token = _new_token()
    _set(db, HASH_KEY, _hash(token))
    db.commit()
    _write_file(path, token)
    logger.info("AI key reset")


# ---------------------------------------------------------------------------
# Restore: the key and switch in use stay, whatever the backup held
# ---------------------------------------------------------------------------
def snapshot(db: Session) -> dict:
    return {HASH_KEY: _get(db, HASH_KEY), ACCESS_KEY: _get(db, ACCESS_KEY)}


def carry_over(db: Session, before: dict) -> None:
    """
    After a restore, put back the key hash and switch from before it: an old
    backup must never bring back a key that was since replaced or revoked, or
    turn access back on.
    """
    for key, value in before.items():
        _set(db, key, value)
    db.commit()
    sync(db)


# ---------------------------------------------------------------------------
# Checking a request
# ---------------------------------------------------------------------------
class KeyRefused(Exception):
    """A key was presented but can't be used; the message says why."""


def bearer_token(authorization: Optional[str]) -> Optional[str]:
    if authorization and authorization[:7].lower() == "bearer ":
        return authorization[7:].strip() or None
    return None


def check_key(token: str, client_host: Optional[str], db: Session) -> None:
    """Accept or raise KeyRefused. Refusals are logged without the key."""
    if mode() == "mac" and client_host not in LOCAL_HOSTS:
        logger.warning("AI key refused: request from %s, not this computer", client_host)
        raise KeyRefused("The AI key only works from this computer.")
    stored = _get(db, HASH_KEY)
    if not stored or not hmac.compare_digest(stored, _hash(token)):
        logger.warning("AI key refused from %s: not the current key", client_host)
        raise KeyRefused("AI key not accepted: it was replaced or revoked, or was copied wrong.")
    if not access_on(db):
        logger.info("AI key refused: AI access is turned off")
        raise KeyRefused(TURNED_OFF)
