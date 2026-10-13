"""
How much one JSON entry import request (/api/import/entries, the AI
connector's preview_transactions and add_transactions) may ask for.

Both routes hold SQLite's write lock while they work, and each row dated
before the ledger's latest entry replays the whole ledger, so a long
request kept the owner's own saves (turning AI access off included)
waiting until they failed with "database is locked". With the AI key a
request takes at most AI_MAX_ROWS rows and replays at most AI_MAX_REPLAYED
entries. A login (the owner, scripts) keeps MAX_ROWS, and the CSV import is
unchanged. The body's size limit, for every route: test_body_limit.py.
"""

import importlib.util
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import entry_import
from backend.routers.entry_import import AI_MAX_REPLAYED, AI_MAX_ROWS
from backend.services import first_run, outbound
from backend.services.csv_import import CSV_COLUMNS

PREVIEW = "/api/import/entries/preview"
EXECUTE = "/api/import/entries/execute"


def cash_deposits(count: int, start: datetime) -> list[dict]:
    """USD deposits into Bank, an hour apart, each of another amount."""
    return [
        {"date": (start + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M:%SZ"), "type": "Deposit",
         "amount": str(100 + i), "from_account": "External", "to_account": "Bank"}
        for i in range(count)
    ]


def buys(count: int, start: datetime, every: timedelta = timedelta(hours=6)) -> list[dict]:
    return [
        {"date": (start + i * every).strftime("%Y-%m-%dT%H:%M:%SZ"), "type": "Buy",
         "amount": "0.001", "from_account": "Bank", "to_account": "Exchange BTC",
         "cost_basis_usd": f"{30 + i}.00", "fee_amount": "0.50", "fee_currency": "USD"}
        for i in range(count)
    ]


@pytest.fixture
def empty_ledger(auth_client, ai_key_headers):
    """The session's ledger, emptied; yields the owner's client and a
    client with only the AI key."""
    auth_client.delete("/api/transactions/delete_all")
    yield auth_client, TestClient(app, headers=ai_key_headers)
    auth_client.delete("/api/transactions/delete_all")


def count(client) -> int:
    return len(client.get("/api/transactions").json())


# The row cap with the AI key
@pytest.mark.parametrize("url", [PREVIEW, EXECUTE])
def test_over_the_cap_with_the_ai_key_is_refused_naming_it(empty_ledger, url):
    owner, ai = empty_ledger
    r = ai.post(url, json={"rows": cash_deposits(AI_MAX_ROWS + 1, datetime(2024, 1, 1, tzinfo=timezone.utc))})
    assert r.status_code == 400
    assert r.json()["detail"].startswith(f"Too many transactions. Maximum is {AI_MAX_ROWS} rows per request "
                                         "with the AI key: send them in smaller groups")
    assert count(owner) == 0


def test_at_the_cap_the_ai_key_previews_and_adds(empty_ledger):
    owner, ai = empty_ledger
    rows = cash_deposits(AI_MAX_ROWS, datetime(2024, 1, 1, tzinfo=timezone.utc))
    preview = ai.post(PREVIEW, json={"rows": rows})
    assert preview.status_code == 200, preview.text
    assert preview.json()["ready_count"] == AI_MAX_ROWS
    added = ai.post(EXECUTE, json={"rows": rows})
    assert added.status_code == 200, added.text
    assert count(owner) == AI_MAX_ROWS


def test_a_login_keeps_the_larger_limit(empty_ledger):
    owner, ai = empty_ledger
    rows = cash_deposits(AI_MAX_ROWS + 1, datetime(2024, 1, 1, tzinfo=timezone.utc))
    r = owner.post(PREVIEW, json={"rows": rows})
    assert r.status_code == 200, r.text
    assert r.json()["ready_count"] == AI_MAX_ROWS + 1


def test_the_owners_csv_import_is_unchanged(empty_ledger):
    owner, ai = empty_ledger
    lines = [",".join(CSV_COLUMNS)] + [
        f"{row['date']},Deposit,{row['amount']},External,Bank,,,,,,,"
        for row in cash_deposits(AI_MAX_ROWS + 1, datetime(2024, 1, 1, tzinfo=timezone.utc))
    ]
    csv = ("\n".join(lines) + "\n").encode()
    r = owner.post("/api/import/execute", files={"file": ("big.csv", csv, "text/csv")})
    assert r.status_code == 200, r.text
    assert count(owner) == AI_MAX_ROWS + 1


# Rows dated before the ledger's latest entry, with the AI key
def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")


@pytest.fixture
def reference(fresh_app, monkeypatch):
    """The reference test ledger (testdata/reference_ledger.json) on a
    database of its own, price source Off; yields the owner's client and a
    client with only the AI key."""
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    owner = TestClient(app)
    seed_ledger.log_in(owner, "seed-user", "seed-password-123", first_run.ensure_code())
    assert seed_ledger.seed(owner) == len(seed_ledger.ledger_rows())
    assert owner.put("/api/settings/ai-access", json={"on": True}).status_code == 200
    key = owner.post("/api/settings/ai-key").json()["key"]
    yield owner, TestClient(app, headers={"Authorization": f"Bearer {key}"})


BEFORE_IT_ALL = datetime(2022, 1, 3, 15, tzinfo=timezone.utc)  # the reference ledger starts in 2023


def largest_allowed(ledger_size: int) -> int:
    """The most rows dated before the ledger's latest entry one AI request may send."""
    rows = 1
    while rows + 1 <= max(1, AI_MAX_REPLAYED // (ledger_size + rows + 1)):
        rows += 1
    return rows


def test_too_many_earlier_rows_with_the_ai_key_are_refused_saying_how_many(reference):
    owner, ai = reference
    size = count(owner)
    allowed = largest_allowed(size)
    too_many = buys(allowed + 1, BEFORE_IT_ALL)
    for url in (PREVIEW, EXECUTE):
        r = ai.post(url, json={"rows": too_many})
        assert r.status_code == 400, (url, r.text)
        detail = r.json()["detail"]
        assert detail.startswith("Too many rows dated before the ledger's latest entry (2026-09-16T12:00:00Z)")
        assert f"Send at most {AI_MAX_REPLAYED // (size + allowed + 1)} of them per request" in detail
    assert count(owner) == size
    assert owner.post(PREVIEW, json={"rows": too_many}).status_code == 200  # a login: no such limit


def test_rows_dated_after_the_ledger_dont_count(reference):
    owner, ai = reference
    later = buys(AI_MAX_ROWS, datetime(2026, 9, 17, tzinfo=timezone.utc), every=timedelta(minutes=30))
    r = ai.post(PREVIEW, json={"rows": later})
    assert r.status_code == 200, r.text
    assert r.json()["ready_count"] == AI_MAX_ROWS


def test_one_earlier_row_is_always_allowed(reference, monkeypatch):
    """However large the ledger: one row costs one recalculation, as an edit
    made in BitcoinTX does."""
    owner, ai = reference
    monkeypatch.setattr(entry_import, "AI_MAX_REPLAYED", 10)
    assert ai.post(PREVIEW, json={"rows": buys(1, BEFORE_IT_ALL)}).status_code == 200
    assert ai.post(PREVIEW, json={"rows": buys(2, BEFORE_IT_ALL)}).status_code == 400


def test_the_owners_save_during_the_largest_ai_preview_allowed_goes_through(reference):
    """SQLite's other writers wait 5 s for the lock. Here the largest preview
    the key may ask for takes about 1.6 s, and the owner turning AI access
    off meanwhile waits for it, then succeeds. Before the limits, a preview
    of 100 such rows held the lock about 14 s and that save failed with
    "database is locked"."""
    owner, ai = reference
    rows = buys(largest_allowed(count(owner)), BEFORE_IT_ALL)
    preview = {}

    def run_preview():
        preview["response"] = ai.post(PREVIEW, json={"rows": rows})
        preview["ended"] = time.monotonic()

    worker = threading.Thread(target=run_preview)
    worker.start()
    time.sleep(0.3)  # the preview is replaying the ledger, holding the write lock
    started = time.monotonic()
    r = owner.put("/api/settings/ai-access", json={"on": False})
    worker.join()

    assert preview["response"].status_code == 200, preview["response"].text
    assert started < preview["ended"]  # the save was asked for during the preview
    assert r.status_code == 200, r.text
    assert owner.get("/api/settings/ai-access").json()["on"] is False
