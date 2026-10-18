"""
Two imports of the same rows at once save them once (#454). The AI's add
sent again while the first still runs (the connector gives up after 120 s,
the server doesn't, and the ledger guide says a resend is safe), or two
browser tabs importing the same River or CSV file: each request checked the
ledger for its rows, then wrote, so the second checked before the first had
committed and saved them again. The check and the writes now hold one write
lock; the prices are found before it, as before (#426).

A barrier stands for what both requests wait for before they save (the
price download): it only makes them leave it together. For the AI's add,
whose check came before its writes' price step, each request's first write
also waits a moment for the other's check (checked_then_written).
"""

import threading

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import csv_import, entry_import
from backend.services.csv_import import CSV_COLUMNS
from backend.tests.conftest import stub_daily_prices
from backend.tests.test_ai_copies import ledger, made_before_changing, transaction_ids  # noqa: F401  (fixture)

ROW = {"date": "2024-03-05T14:30:00Z", "type": "Deposit", "amount": "0.01",
       "from_account": "External", "to_account": "Wallet", "source": "Income"}
RIVER_ROW = {"date": "2026-01-05T12:00:00Z", "type": "Buy", "amount": "0.0003",
             "from_account": "Exchange USD", "to_account": "Exchange BTC", "cost_basis_usd": "25.00"}
CSV = (",".join(CSV_COLUMNS) + "\n2024-01-05T12:00:00Z,Deposit,1000,External,Bank,,,,,,,\n").encode()


@pytest.fixture
def clean(auth_client, monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 50000)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield auth_client
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def both_wait(monkeypatch, target: str) -> None:
    """Each request's first call of `target` (the step that waits for the
    price download) waits for the other's, so both leave it together."""
    module, name = target.rsplit(".", 1)
    real = getattr(__import__(module, fromlist=[name]), name)
    barrier, waited = threading.Barrier(2), threading.local()

    def wait_then(*args, **kwargs):
        if not getattr(waited, "done", False):
            waited.done = True
            barrier.wait(timeout=10)
        return real(*args, **kwargs)

    async def wait_then_async(*args, **kwargs):
        if not getattr(waited, "done", False):
            waited.done = True
            barrier.wait(timeout=10)
        return await real(*args, **kwargs)

    monkeypatch.setattr(target, wait_then_async if name == "autofill_fmv" else wait_then)


def checked_then_written(monkeypatch) -> None:
    """Each request's first write waits (1 s at most) until two duplicate
    checks are done: before, each request checked once, with the lock free,
    so both checked and both wrote; now the other's check waits behind this
    request's lock, so the wait runs out and this one commits first. (With
    the key a request checks twice itself, writable_now then write_rows, so
    nothing waits: the lock alone keeps the two apart.)"""
    checks, done = threading.Condition(), [0]
    for target in ("backend.services.entry_import.mark_duplicates", "backend.routers.entry_import.mark_duplicates"):
        module, name = target.rsplit(".", 1)
        real = getattr(__import__(module, fromlist=[name]), name)

        def counted(*args, real=real, **kwargs):
            out = real(*args, **kwargs)
            with checks:
                done[0] += 1
                checks.notify_all()
            return out

        monkeypatch.setattr(target, counted)
    real_create, wrote = entry_import.create_transaction_record, threading.local()

    def create(*args, **kwargs):
        if not getattr(wrote, "done", False):
            wrote.done = True
            with checks:
                checks.wait_for(lambda: done[0] >= 2, timeout=1)
        return real_create(*args, **kwargs)

    monkeypatch.setattr(entry_import, "create_transaction_record", create)


def at_once(send) -> list:
    """send() from two threads at once; their answers."""
    out = []
    threads = [threading.Thread(target=lambda: out.append(send())) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return out


def ledger_size(client) -> int:
    return len(client.get("/api/transactions").json())


@pytest.mark.parametrize("who", ["owner", "ai"])
def test_two_adds_of_the_same_rows_at_once_save_them_once(clean, ai_key_headers, monkeypatch, who):
    client = clean if who == "owner" else TestClient(app, headers=ai_key_headers)
    both_wait(monkeypatch, "backend.routers.entry_import.autofill_fmv")
    checked_then_written(monkeypatch)
    out = at_once(lambda: client.post("/api/import/entries/execute", json={"rows": [ROW]}))
    assert [r.status_code for r in out] == [200, 200], [r.text for r in out]
    assert sorted(r.json()["imported_count"] for r in out) == [0, 1]
    assert sorted(r.json()["skipped_duplicates"] for r in out) == [0, 1]
    assert ledger_size(clean) == 1  # was 2


def test_two_river_imports_of_the_same_rows_at_once_save_them_once(clean, monkeypatch):
    both_wait(monkeypatch, "backend.services.csv_import.find_prices_first")
    out = at_once(lambda: clean.post("/api/import/river/execute", json={"rows": [RIVER_ROW]}))
    assert [r.status_code for r in out] == [200, 200], [r.text for r in out]
    assert sorted(r.json()["message"] for r in out) == [
        "Imported 1 transaction(s).", "Nothing to import — 1 row(s) already exist in the ledger."]
    assert ledger_size(clean) == 1  # was 2


def test_two_csv_imports_into_an_empty_ledger_at_once_save_one(clean, monkeypatch):
    both_wait(monkeypatch, "backend.services.csv_import.find_prices_first")
    out = at_once(lambda: clean.post("/api/import/execute", files={"file": ("x.csv", CSV, "text/csv")}))
    assert sorted(r.status_code for r in out) == [200, 400], [r.text for r in out]
    [refused] = [r for r in out if r.status_code == 400]
    assert refused.json()["detail"] == (
        "Import failed: Database has 1 existing transaction(s). Please delete all transactions before "
        "importing. No transactions were saved.")
    assert ledger_size(clean) == 1  # was 2


def test_an_ai_add_a_save_made_meanwhile_dates_earlier_comes_after_a_copy(ledger, monkeypatch):  # noqa: F811
    """A row dated after the ledger's latest makes no AI copy, but a save
    made before the add takes the lock, of a later row, makes it one that
    recalculates the ledger (#414): the copy is made then, under the lock,
    holding the ledger as the add found it."""
    path, ids, owner, ai = ledger
    real, once = entry_import.find_prices_first, []

    def later_row_saved_meanwhile(db, rows):
        if not once:
            once.append(True)
            later = {"type": "Deposit", "timestamp": "2024-05-15T17:00:00Z", "from_account_id": 99,
                     "to_account_id": 1, "amount": "700", "fee_amount": "0", "fee_currency": "USD"}
            assert owner.post("/api/transactions", json=later).status_code == 200
        return real(db, rows)

    monkeypatch.setattr(entry_import, "find_prices_first", later_row_saved_meanwhile)
    row = {"date": "2024-04-15T17:00:00Z", "type": "Deposit", "amount": "500", "from_account": "External",
           "to_account": "Bank", "source": "N/A"}
    r = ai.post("/api/import/entries/execute", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [copy] = made_before_changing(path)  # was none
    assert len(transaction_ids(copy)) == 4 and r.json()["created"][0]["id"] not in transaction_ids(copy)


def test_an_add_that_cant_have_the_lock_saves_nothing(clean, monkeypatch):
    monkeypatch.setattr(entry_import, "take_write_lock", lambda db: False)
    r = clean.post("/api/import/entries/execute", json={"rows": [ROW]})
    assert (r.status_code, r.json()["detail"]) == (
        503, "Not added: BitcoinTX was busy saving something else, and nothing was saved. Try again.")
    assert ledger_size(clean) == 0


@pytest.mark.parametrize("url,request_", [
    ("/api/import/river/execute", {"json": {"rows": [RIVER_ROW]}}),
    ("/api/import/execute", {"files": {"file": ("x.csv", CSV, "text/csv")}}),
])
def test_an_import_that_cant_have_the_lock_saves_nothing(clean, monkeypatch, url, request_):
    monkeypatch.setattr(csv_import, "take_write_lock", lambda db: False)
    r = clean.post(url, **request_)
    assert (r.status_code, r.json()["detail"]) == (
        503, "Import failed: BitcoinTX was busy saving something else, and no transactions were saved. Try again.")
    assert ledger_size(clean) == 0

