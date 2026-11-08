"""
The connector reads a time given with no timezone in the tax timezone by the
tzdata package's rules alone, as BitcoinTX itself does since #889 (#908):
never the AI computer's own zone files, which Python's zoneinfo reads first.
On a computer whose files are older than the package's (Winnipeg keeps
summer time from 1 November 2026, since IANA's 2026 releases), a sale the AI
moved to 23:30 on 15 November 2026 was saved an hour late, on the 16th. The
other zones whose rules changed in 2026 (British Columbia, Alberta, Cuba,
Morocco: docs/CHANGELOG.md) go through the same read.
"""

import json
import os
import subprocess
import sys
from importlib import resources
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Run in a process of its own, with the planted zone files first in
# PYTHONTZPATH and nothing of the backend's imported (its import makes the
# switch for the app, and would hide the connector's). BitcoinTX answers
# America/Winnipeg as the tax timezone, and lists one row, saved at 05:30
# UTC on 16 November 2026: 00:30 that day in Winnipeg by 2026f's rules,
# 23:30 the day before by the old ones.
CHECK = """
import asyncio, json, zoneinfo
from btctx_mcp import server

async def answer(method, path, **kwargs):
    if path == "/api/settings/tax-timezone":
        return {"timezone": "America/Winnipeg", "source": "setting"}
    if path == "/api/transactions":
        return [{"id": 1, "timestamp": "2026-11-16T05:30:00Z", "type": "Sell", "amount": "0.1",
                 "from_account_id": 4, "to_account_id": 3}]
    raise AssertionError(path)

class Names:
    def name(self, account_id):
        return str(account_id)

async def names(fresh=False):
    return Names()

server._call = answer
server._account_names = names
server._version.update(checked=True, notice=None)

async def listed(**dates):
    return [tx["id"] for tx in (await server.list_transactions(**dates))["transactions"]]

async def main():
    return {
        "tzpath": list(zoneinfo.TZPATH),
        "date": await server._timestamp_from("2026-11-15 23:30"),
        "acquired_at": await server._date_from("2026-11-15 23:30"),
        "price": await server._price_query("2026-11-15 23:30"),
        "through_the_15th": await listed(end_date="2026-11-15"),
        "from_the_16th": await listed(start_date="2026-11-16"),
    }

print(json.dumps(asyncio.run(main())))
"""


@pytest.fixture
def old_zone_files(tmp_path) -> Path:
    """A computer's own zone files from before 2026f: its Winnipeg is the
    package's Chicago, the offsets and clock changes Winnipeg had since 2007."""
    chicago = resources.files("tzdata").joinpath("zoneinfo", "America", "Chicago").read_bytes()
    (tmp_path / "America").mkdir()
    (tmp_path / "America" / "Winnipeg").write_bytes(chicago)
    return tmp_path


def test_every_zone_read_takes_the_packages_rules(old_zone_files):
    env = {**os.environ, "PYTHONTZPATH": str(old_zone_files), "PYTHONPATH": str(ROOT / "mcp_server")}
    done = subprocess.run([sys.executable, "-c", CHECK], cwd=ROOT, env=env,
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr[-2000:]
    # 23:30 in Winnipeg on 15 November 2026 is 04:30 UTC (summer time kept),
    # not 05:30; and the row at 05:30 UTC is on the 16th there, not the 15th
    assert json.loads(done.stdout) == {
        "tzpath": [],
        "date": "2026-11-16T04:30:00+00:00",          # update_transaction's date
        "acquired_at": "2026-11-16T04:30:00+00:00",   # and its acquired_at given with a time
        "price": {"at": "2026-11-16T04:30:00+00:00"},  # get_btc_price at a time
        "through_the_15th": [],                        # list_transactions' end_date
        "from_the_16th": [1],                          # and its start_date
    }
