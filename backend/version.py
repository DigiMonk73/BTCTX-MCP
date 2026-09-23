"""
backend/version.py

The BitcoinTX version, read from the VERSION file at the project root (the
single source for the app, the Docker image, the macOS app and the StartOS
package). The Docker image copies it to /app/VERSION and the macOS app bundles
it beside backend/.
"""

from functools import lru_cache
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


@lru_cache(maxsize=1)
def app_version() -> str:
    try:
        return VERSION_FILE.read_text().strip() or "unknown"
    except OSError:
        return "unknown"
