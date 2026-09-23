"""
backend/secret_key.py

The session-cookie signing key. Anyone who knows it can forge a login cookie,
so it must never be a value published in this repo.

Order: SECRET_KEY env var (unless it's a known public default) -> a random
key generated once and stored next to the database (DATABASE_FILE's folder:
/data on Docker/StartOS, Application Support on macOS), readable only by the
app's user. Stable across restarts, unique per install.
"""

import logging
import os
import secrets

logger = logging.getLogger(__name__)

KEY_FILENAME = ".btctx_secret_key"

# Values that have appeared in this repo — treated as unset.
PUBLIC_DEFAULTS = {
    "",
    "default_secret_key",
    "desktop-app-secret-key-change-in-production",
}


def load_secret_key(data_dir: str) -> str:
    env_key = os.getenv("SECRET_KEY", "")
    if env_key not in PUBLIC_DEFAULTS:
        return env_key

    path = os.path.join(data_dir, KEY_FILENAME)
    try:
        with open(path, encoding="utf-8") as fh:
            key = fh.read().strip()
        if len(key) >= 32:
            return key
    except FileNotFoundError:
        pass

    key = secrets.token_urlsafe(48)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Another worker created it first; use theirs
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(key)
    logger.info("Generated a new session secret key at %s", path)
    return key
