"""
The tax timezone's rules come from the pinned tzdata package alone, on every
machine (#889): never the computer's own zone files, which zoneinfo reads
first (Debian's in the Docker image and so on StartOS, macOS's in the Mac
app), so a base-image or macOS update can't move a tax figure.
"""

import os
import subprocess
import sys
import zoneinfo
from importlib import resources
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Each entry point's first import: the server (uvicorn, Docker's CMD), the
# CLI (StartOS's actions, `docker exec`), the migrations (every start), and
# the tax timezone's own module, which the Mac app reaches through the server
ENTRY_POINTS = ["backend.main", "backend.cli", "backend.migrate", "backend.services.tax_time"]

# Run after one entry point's import, with the planted zone files first in
# PYTHONTZPATH: Chicago's offset on 1 January 2025 (the package's: UTC-6;
# the planted file's: Tokyo's, UTC+9), its tax year's start, and whether
# `localtime`, a name only a Linux system's files hold, reads.
CHECK = """
import importlib, sys, zoneinfo
from datetime import datetime, timezone
importlib.import_module(sys.argv[1])
from backend.services import tax_time
chicago = zoneinfo.ZoneInfo("America/Chicago")
print(zoneinfo.TZPATH, datetime(2025, 1, 1, tzinfo=chicago).utcoffset().total_seconds() / 3600,
      tax_time.tax_year_bounds(2025, chicago)[0].isoformat(), tax_time.readable_zone("localtime"))
"""


@pytest.fixture(scope="module")
def planted_zone_files(tmp_path_factory) -> Path:
    """A computer's own zone files whose Chicago has Tokyo's rules, and a
    `localtime` beside it, as Debian's files have."""
    folder = tmp_path_factory.mktemp("zoneinfo")
    tokyo = resources.files("tzdata").joinpath("zoneinfo", "Asia", "Tokyo").read_bytes()
    (folder / "America").mkdir()
    (folder / "America" / "Chicago").write_bytes(tokyo)
    (folder / "localtime").write_bytes(tokyo)
    return folder


@pytest.mark.parametrize("entry_point", ENTRY_POINTS)
def test_every_entry_point_reads_the_pinned_package_only(planted_zone_files, entry_point, tmp_path):
    env = {**os.environ, "PYTHONTZPATH": str(planted_zone_files), "DATABASE_FILE": str(tmp_path / "btctx.db")}
    env.pop("BTCTX_TIMEZONE", None)
    done = subprocess.run([sys.executable, "-c", CHECK, entry_point], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.split() == ["()", "-6.0", "2025-01-01T06:00:00+00:00", "None"]


# The second calculation (scripts/independent_figures.py) imports nothing of
# the backend's, so it switches on its own (#908). Loaded as its test loads
# it, in a process the backend's import hasn't switched: Chicago's offset on
# 1 January 2025 by its tax timezone's reading.
SECOND_CALCULATION = """
import importlib.util, sys, zoneinfo
from datetime import datetime
spec = importlib.util.spec_from_file_location("independent_figures", sys.argv[1])
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
chicago = module._tax_zone("America/Chicago")
print(zoneinfo.TZPATH, datetime(2025, 1, 1, tzinfo=chicago).utcoffset().total_seconds() / 3600)
"""


def test_the_second_calculation_reads_the_pinned_package_only(planted_zone_files):
    env = {**os.environ, "PYTHONTZPATH": str(planted_zone_files)}
    done = subprocess.run([sys.executable, "-c", SECOND_CALCULATION, str(ROOT / "scripts" / "independent_figures.py")],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    assert done.stdout.split() == ["()", "-6.0"]


def test_the_tests_read_the_pinned_package_only():
    """The suite's own process (conftest imports the server first)."""
    assert zoneinfo.TZPATH == ()


def test_the_mac_app_bundles_the_package():
    """The frozen app imports `backend` like the server, and with no system
    files to fall back on needs tzdata inside it: named here, PyInstaller's
    own hook for it bundles its zone files (the 2.0.0 app holds them)."""
    spec = (ROOT / "desktop" / "BitcoinTX.spec").read_text(encoding="utf-8")
    assert '"tzdata",' in spec
