"""
backend/secret_key.py

The session-cookie signing key. Anyone who knows it can forge a login cookie,
so it must never be a value published in this repo.

Order: SECRET_KEY env var (unless it's a known public default) -> a random
key generated once and stored next to the database (DATABASE_FILE's folder:
/data on Docker/StartOS, Application Support on macOS), readable only by the
app's user. Stable across restarts, unique per install. A key file that is
empty or too short to be one of ours is replaced with a new key (everyone
logs in again).
"""

import logging
import os
import secrets
import tempfile
from typing import Optional

logger = logging.getLogger(__name__)

KEY_FILENAME = ".btctx_secret_key"
MIN_KEY_LENGTH = 32

# Values that have appeared in this repo (or its history) — treated as unset.
PUBLIC_DEFAULTS = {
    "",
    "default_secret_key",
    "desktop-app-secret-key-change-in-production",
    "replace_this_with_a_strong_random_value",  # .env.example placeholder
    "your_secret_key_here",
    "CHANGEME-REPLACE-WITH-STRONG-SECRET",
}


def _read_key(path: str) -> Optional[str]:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        return None


def load_secret_key(data_dir: str) -> str:
    env_key = os.getenv("SECRET_KEY", "")
    if env_key not in PUBLIC_DEFAULTS:
        return env_key

    path = os.path.join(data_dir, KEY_FILENAME)
    key = _read_key(path)
    if key is not None and len(key) >= MIN_KEY_LENGTH:
        return key

    new_key = secrets.token_urlsafe(48)
    if key is None:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            # Another worker created it first; use theirs
            key = _read_key(path)
            if key is not None and len(key) >= MIN_KEY_LENGTH:
                return key
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(new_key)
            logger.info("Generated a new session secret key at %s", path)
            return new_key

    # Empty or too short (a truncated write, or one put there by hand): a key
    # anyone could guess. Replace it in one step, owner-only like the first.
    fd, tmp = tempfile.mkstemp(dir=data_dir, prefix=KEY_FILENAME + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(new_key)
    os.replace(tmp, path)
    logger.warning(
        "The session secret key in %s was empty or too short; replaced it with a new one "
        "(everyone has to log in again).", path
    )
    return new_key
