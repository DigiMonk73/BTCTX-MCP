"""
The BitcoinTX version, read from the VERSION file at the project root (the
single source for the app, the Docker image, the macOS app and the StartOS
package). The Docker image copies it to /app/VERSION and the macOS app bundles
it beside backend/.
"""

import re
from functools import lru_cache
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
# A 2.0 pre-release (2.0 plan 7.4, B10a): on a Mac, BitcoinTX Beta
BETA = re.compile(r"\d+\.\d+\.\d+-beta\.[1-9]\d*")


@lru_cache(maxsize=1)
def app_version() -> str:
    try:
        return VERSION_FILE.read_text().strip() or "unknown"
    except OSError:
        return "unknown"


def is_beta_version(version: str) -> bool:
    """Whether `version` is a 2.0 pre-release, X.Y.Z-beta.N."""
    return BETA.fullmatch(version) is not None
