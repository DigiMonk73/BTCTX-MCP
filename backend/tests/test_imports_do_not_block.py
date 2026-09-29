"""
Bug hunt 2026-09-29: the import endpoints were `async def` but did their
ledger work (parsing, the MCP dry run, the write) right on the event loop,
so while one ran the server answered nothing else, not even /api/health
(StartOS's health check): a dry run of 20 backdated rows on a
600-transaction ledger froze it for 10 s. That work now runs in a worker
thread.

Here the step doing each endpoint's work is made to take a second, and
/api/health, asked meanwhile, must answer at once.
"""

import asyncio
import time

import httpx
import pytest

from backend.main import app
from backend.services.csv_import import CSV_COLUMNS
from backend.tests.conftest import stub_daily_prices

WORK_S = 1.0

CSV = (",".join(CSV_COLUMNS) + "\n2024-01-05T12:00:00Z,Deposit,1000,External,Bank,,,,,,,\n").encode()
RIVER_CSV = (b"Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag\n"
             b"2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy\n")
ENTRY = {"date": "2024-01-05T12:00:00Z", "type": "Deposit", "amount": "1000",
         "from_account": "External", "to_account": "Bank"}
RIVER_ROW = {"date": "2026-01-05T12:00:00Z", "type": "Buy", "amount": "0.0003",
             "from_account": "Exchange USD", "to_account": "Exchange BTC", "cost_basis_usd": "25.00"}

# endpoint: (the step that does its work, the request)
CASES = {
    "MCP dry run": ("backend.routers.entry_import.simulate",
                    ("/api/import/entries/preview", {"json": {"rows": [ENTRY]}})),
    "MCP add": ("backend.routers.entry_import.write_rows",
                ("/api/import/entries/execute", {"json": {"rows": [ENTRY]}})),
    "CSV preview": ("backend.routers.csv_import.parse_csv_file",
                    ("/api/import/preview", {"files": {"file": ("x.csv", CSV, "text/csv")}})),
    "CSV import": ("backend.routers.csv_import.execute_import",
                   ("/api/import/execute", {"files": {"file": ("x.csv", CSV, "text/csv")}})),
    "River preview": ("backend.routers.river_import.annotate_duplicates",
                      ("/api/import/river/preview", {"files": {"file": ("r.csv", RIVER_CSV, "text/csv")}})),
    "River import": ("backend.routers.river_import.execute_import",
                     ("/api/import/river/execute", {"json": {"rows": [RIVER_ROW]}})),
}


@pytest.fixture
def clean(auth_client, monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 50000)
    auth_client.delete("/api/transactions/delete_all")
    yield auth_client
    auth_client.delete("/api/transactions/delete_all")


@pytest.mark.parametrize("case", list(CASES))
def test_an_import_does_not_stop_the_server_answering(clean, monkeypatch, case):
    step, (url, request) = CASES[case]
    module, name = step.rsplit(".", 1)
    work = getattr(__import__(module, fromlist=[name]), name)

    def slow_work(*args, **kwargs):
        time.sleep(WORK_S)  # blocks whatever thread runs it, like real ledger work
        return work(*args, **kwargs)

    monkeypatch.setattr(step, slow_work)

    async def main():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver",
                                     cookies=dict(clean.cookies)) as c:
            async def run_import():
                r = await c.post(url, **request)
                assert r.status_code == 200, r.text

            async def health():
                # Asked 0.2 s into the import's work; the clock starts
                # before the wait, as a blocked event loop delays the wait too
                start = time.monotonic()
                await asyncio.sleep(0.2)
                assert (await c.get("/api/health")).status_code == 200
                return time.monotonic() - start - 0.2

            _, waited = await asyncio.gather(run_import(), health())
            return waited

    waited = asyncio.run(main())
    assert waited < 0.5, f"/api/health waited {waited:.2f}s for the {case}"
