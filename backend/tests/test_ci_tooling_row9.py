"""
Row 9's tooling (#972): the .dmg check tried again when hdiutil can't open
the image it just made (#946), and the IRS forms watch every day in December
and January, when the next year's final forms usually come.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
MAC_APP = ROOT / "scripts" / "mac-app.sh"
IRS_WATCH = (ROOT / ".github" / "workflows" / "irs-forms-watch.yml").read_text()

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

# A stand-in hdiutil: `verify` fails the first $FAILS times as #946's did, then passes
FAKE_HDIUTIL = """#!/usr/bin/env bash
count_file="$FAKE_DIR/verify-count"
n=$(( $(cat "$count_file" 2>/dev/null || echo 0) + 1 ))
echo "$n" > "$count_file"
if [ "$1" = verify ] && [ "$n" -le "$FAILS" ]; then
  echo "hdiutil: verify failed - Resource temporarily unavailable" >&2
  exit 1
fi
echo "checksum of \\"$2\\" is VALID" >&2
"""


def verify(tmp_path: Path, fails: int) -> tuple[subprocess.CompletedProcess, int]:
    """mac-app.sh's verify_dmg with the stand-in: its result and how often it verified."""
    fake = tmp_path / "hdiutil"
    fake.write_text(FAKE_HDIUTIL)
    fake.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}", "FAKE_DIR": str(tmp_path),
           "FAILS": str(fails), "DMG_VERIFY_PAUSE": "0"}
    run = subprocess.run(["bash", "-c", f'source "{MAC_APP}" && verify_dmg BitcoinTX-macOS.dmg'],
                         env=env, capture_output=True, text=True, timeout=30)
    return run, int((tmp_path / "verify-count").read_text())


def test_a_dmg_hdiutil_cant_open_yet_is_verified_again(tmp_path):
    run, tries = verify(tmp_path, fails=1)
    assert run.returncode == 0, run.stderr
    assert tries == 2 and "is VALID" in run.stderr


def test_a_dmg_that_never_verifies_still_fails(tmp_path):
    run, tries = verify(tmp_path, fails=99)
    assert run.returncode != 0
    assert tries == 5 and "verify failed 5 times" in run.stderr


def test_the_package_step_verifies_through_it():
    script = MAC_APP.read_text()
    assert 'verify_dmg "$stem.dmg"' in script
    assert 'hdiutil verify "$stem' not in script  # only through verify_dmg


def test_the_irs_watch_runs_daily_in_december_and_january():
    assert 'cron: "0 14 * 12,1 *"' in IRS_WATCH
    assert 'cron: "0 14 * 2-11 1"' in IRS_WATCH
