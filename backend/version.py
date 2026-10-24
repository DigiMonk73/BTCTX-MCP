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
# A 2.0 pre-release, an alpha or a beta (2.0 plan 7.4, B10a; #251's
# decision 28): on a Mac, BitcoinTX Preview
PRERELEASE = re.compile(r"\d+\.\d+\.\d+-(alpha|beta)\.[1-9]\d*")


@lru_cache(maxsize=1)
def app_version() -> str:
    try:
        return VERSION_FILE.read_text().strip() or "unknown"
    except OSError:
        return "unknown"


def is_prerelease_version(version: str) -> bool:
    """Whether `version` is a 2.0 pre-release, X.Y.Z-alpha.N or X.Y.Z-beta.N."""
    return PRERELEASE.fullmatch(version) is not None
