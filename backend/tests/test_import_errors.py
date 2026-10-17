"""
An unexpected failure of the CSV or River import (not a row the ledger
refused) answers one fixed sentence, as the restore answers in plain words:
the error's own text can carry SQL, a server path or a transaction's date.
The log names the error's type, its trace only at DEBUG (#204).
"""

import pytest

from backend.routers.csv_import import IMPORT_FAILED
from backend.tests.conftest import stub_daily_prices
from backend.tests.test_imports_do_not_block import CSV, RIVER_ROW

LEAKY = ("(sqlite3.OperationalError) disk I/O error [SQL: INSERT INTO transactions (timestamp) "
         "VALUES (?)] [parameters: ('2024-01-05 12:00:00',)] /data/btctx.db")
CASES = {
    "CSV import": ("backend.routers.csv_import.execute_import",
                   "/api/import/execute", {"files": {"file": ("x.csv", CSV, "text/csv")}}),
    "River import": ("backend.routers.river_import.execute_import",
                     "/api/import/river/execute", {"json": {"rows": [RIVER_ROW]}}),
}


@pytest.fixture
def clean(auth_client, monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 50000)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield auth_client
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


@pytest.mark.parametrize("case", list(CASES))
def test_an_unexpected_failure_answers_a_fixed_sentence(clean, monkeypatch, caplog, case):
    step, url, request = CASES[case]

    def fails(*args, **kwargs):
        raise RuntimeError(LEAKY)

    monkeypatch.setattr(step, fails)
    with caplog.at_level("INFO"):
        r = clean.post(url, **request)
    assert (r.status_code, r.json()) == (500, {"detail": IMPORT_FAILED})
    assert f"{case} failed: RuntimeError" in caplog.text
    assert "2024-01-05" not in caplog.text and "/data/" not in caplog.text
