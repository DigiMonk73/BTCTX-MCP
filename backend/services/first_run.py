"""
The login every install starts with (admin / password, seeded by
database.seed_defaults) and the one-time setup code that claiming it needs.

- is_default_account(): does the account still have that login? bcrypt is
  slow on purpose and GET /api/users/setup-status is public, so the answer
  is remembered for the account's (id, username, password hash). Any change
  of the credentials (Register, Settings, the CLI in another process, a
  restored backup) is a new hash, so it is checked again.
- The setup code: the default login is the same everywhere, so logging in
  with it, and claiming the account (Register, or changing the default
  login in Settings), also need a code that only someone who can read the
  server's data folder has (in the Mac app, the Mac account that runs
  BitcoinTX). It is made at startup while the account has the default
  login, kept in <data folder>/setup-code.txt (owner-only, the same across
  restarts) and deleted once the account is claimed. A server prints it to its log; the
  Mac app's own window reads the file instead (desktop/desktop_api.py) to
  set the owner's login, so the Mac app never logs it. StartOS sets a
  generated password before the first start, so its account never has the
  default login.
"""

from __future__ import annotations

import hmac
import logging
import os
import secrets
import string
import threading

from sqlalchemy.orm import Session

from backend.database import DATABASE_FILE
from backend.models.user import User
from backend.services.desktop import is_desktop
from backend.version import app_version, is_prerelease_version

logger = logging.getLogger(__name__)

DEFAULT_USERNAME = "admin"
DEFAULT_PASSWORD = "password"

DATA_DIR = os.path.dirname(DATABASE_FILE)  # tests point this elsewhere
CODE_FILENAME = "setup-code.txt"
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L

_lock = threading.Lock()
_default: dict[tuple[int, str, str], bool] = {}


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


def code_refused(given: str | None) -> str:
    """Why claiming the default login was refused: no setup code, or a wrong one."""
    return ("That setup code is wrong. " if given else "Enter the setup code. ") + _where_the_code_is()


def default_login_refused() -> str:
    """Why the default login was refused without the setup code."""
    # Not "go to Create account": on an older install with data that page would
    # start the ledger over. Log in with the code, then change the password.
    return ("This install still has the default login: enter the setup code as well. "
            + _where_the_code_is() + " Then set your own password in Settings.")


def code_path() -> str:
    return os.path.join(DATA_DIR, CODE_FILENAME)


def read_code() -> str | None:
    """The setup code in its file, or None when there is none."""
    try:
        with open(code_path(), encoding="utf-8") as fh:
            return fh.read().strip() or None
    except FileNotFoundError:
        return None


def ensure_code() -> str:
    """The setup code, made if there is none yet."""
    code = read_code()
    if code is None:
        raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(12))
        code = "-".join(raw[i:i + 4] for i in range(0, 12, 4))
        _write_code(code)
    _log_code(code)
    return code


def check_code(given: str | None) -> bool:
    code = read_code()
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


def prepare(db: Session) -> None:
    """At startup and after a restore: a code while the account has the
    default login, otherwise no code file."""
    user = db.query(User).order_by(User.id).first()
    if user is not None and is_default_account(user):
        ensure_code()
    else:
        clear_code()


def _where_the_code_is() -> str:
    if is_desktop():
        # a 2.0 pre-release is BitcoinTX Preview, with a folder of its own (2.0 plan 7.4, B10a)
        app = "BitcoinTX Preview" if is_prerelease_version(app_version()) else "BitcoinTX"
        return (f"It is in {CODE_FILENAME} in the Mac app's data folder "
                f"(~/Library/Application Support/{app}); the app's own window normally fills it in.")
    return f"It is in the server's log (docker logs <container>) and in {CODE_FILENAME} in the data folder."


def _write_code(code: str) -> None:
    tmp = code_path() + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)  # owner-only also over a leftover file, whose mode open() keeps
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(code + "\n")
    os.replace(tmp, code_path())


def _log_code(code: str) -> None:
    if is_desktop():
        # The window reads the file itself, and the Mac app's log is what a
        # problem report may attach.
        logger.warning("First-run setup code in %s: the BitcoinTX window uses it to set your login", code_path())
        return
    logger.warning(
        "\n\n    First-run setup code: %s (also in %s)\n"
        "    Enter it on the Create account page to set your username and password.\n",
        code, code_path(),
    )


_CODE_CHARS = frozenset(string.ascii_uppercase + string.digits)


def _normalize(code: str) -> str:
    # ASCII only: the code is generated from ASCII, and a non-ASCII letter can never
    # match it. Comparing such a string with hmac raises TypeError, so keep those out.
    return "".join(ch for ch in code.upper() if ch in _CODE_CHARS)
