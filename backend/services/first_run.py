"""
backend/services/first_run.py

The login every install starts with (admin / password, seeded by
database.seed_defaults) and the one-time setup code that claiming it needs.

- is_default_account(): does the account still have that login? bcrypt is
  slow on purpose and GET /api/users/setup-status is public, so the answer
  is remembered for the account's (id, username, password hash). Any change
  of the credentials (Register, Settings, the CLI in another process, a
  restored backup) is a new hash, so it is checked again.
- The setup code: anyone who can reach a fresh Docker or source install
  knows the default login. Logging in with it, and claiming the account
  (Register, or changing the default login in Settings), also need a code
  that only someone who can
  read the server's log or data folder has. It is made at startup while the
  account has the default login, kept in <data folder>/setup-code.txt
  (owner-only, the same across restarts), printed to the log, and deleted
  once the account is claimed. Not in the Mac app, which listens on
  127.0.0.1 only; StartOS sets a generated password at install, so its
  account never has the default login.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import threading
from typing import Dict, Optional, Tuple

from sqlalchemy.orm import Session

from backend.database import DATABASE_FILE
from backend.models.user import User
from backend.services.desktop import is_desktop

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "password"

DATA_DIR = os.path.dirname(DATABASE_FILE)  # tests point this elsewhere
CODE_FILENAME = "setup-code.txt"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L
_WHERE = f"It is in the server's log (docker logs <container>) and in {CODE_FILENAME} in the data folder."
CODE_REQUIRED = "Enter the setup code. " + _WHERE
CODE_WRONG = "That setup code is wrong. " + _WHERE
# Not "go to Create account": on an older install with data that page would
# start the ledger over. Log in with the code, then change the password.
DEFAULT_LOGIN_REFUSED = (
    "This install still has the default login: enter the setup code as well. " + _WHERE
    + " Then set your own password in Settings."
)

_lock = threading.Lock()
_default: Dict[Tuple[int, str, str], bool] = {}


def is_default_account(user: User) -> bool:
    key = (user.id, user.username, user.password_hash)
    with _lock:
        known = _default.get(key)
    if known is not None:
        return known
    result = user.username == DEFAULT_USERNAME and user.verify_password(DEFAULT_PASSWORD)
    with _lock:
        _default.clear()  # one account: only its current credentials matter
        _default[key] = result
    return result


def code_required() -> bool:
    return not is_desktop()


def code_path() -> str:
    return os.path.join(DATA_DIR, CODE_FILENAME)


def _normalize(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _read_code() -> Optional[str]:
    try:
        with open(code_path(), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except FileNotFoundError:
        return None


def ensure_code() -> str:
    """The setup code, made if there is none yet; printed to the log."""
    code = _read_code()
    if code is None:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
        code = "-".join(raw[i:i + 4] for i in range(0, 12, 4))
        tmp = code_path() + ".tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(code + "\n")
        os.replace(tmp, code_path())
    logger.warning(
        "\n\n    First-run setup code: %s (also in %s)\n"
        "    Enter it on the Create account page to set your username and password.\n",
        code, code_path(),
    )
    return code


def check_code(given: Optional[str]) -> bool:
    code = _read_code()
    if code is None:
        # Deleted, or a restored backup brought the default login back
        ensure_code()
        return False
    return bool(given) and hmac.compare_digest(_normalize(given), _normalize(code))


def clear_code() -> None:
    try:
        os.remove(code_path())
        logger.info("First-run setup code removed: the account is set up")
    except FileNotFoundError:
        pass


def needs_code(user: User) -> bool:
    """Changing this account's login needs the setup code."""
    return code_required() and is_default_account(user)


def prepare(db: Session) -> None:
    """At startup and after a restore: a code while the account has the
    default login (and one is needed), otherwise no code file."""
    user = db.query(User).order_by(User.id).first()
    if user is not None and needs_code(user):
        ensure_code()
    else:
        clear_code()
