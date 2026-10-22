"""
The scripts that seed a running server meet the past-year warning (5.8,
5.15; B6b-6): every row of the reference ledger and of the smoke test is in
an earlier tax year, and no switch turns the warning off on a running
server. scripts/seed_ledger.py (post_confirmed) and scripts/smoke_test.py
(create) each confirm a 409 once, with the fingerprint it gives; any other
refusal stays a refusal.
"""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
ROW = {"type": "Deposit", "timestamp": "2024-01-02T12:00:00Z", "from_account_id": 99, "to_account_id": 1,
       "amount": "100", "fee_amount": "0", "fee_currency": "USD"}
WARNING = {"detail": "This adds to tax year 2024, which you may already have filed. Confirm to save it: a copy of "
           "your ledger is made first.", "years": [2024], "changes": [], "pending": [], "recalc_error": None,
           "confirm": "fp-1"}


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")
smoke_test = _script("smoke_test")


def server(refusal: dict | None = None):
    """A stand-in server: an empty ledger; each POST /api/transactions answers
    409 with `refusal` (the warning by default) until it's sent with that
    refusal's confirm. Returns (client, the requests it got)."""
    refusal = WARNING if refusal is None else refusal
    seen: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}{'?' + request.url.query.decode() if request.url.query else ''}")
        if request.method == "GET":
            return httpx.Response(200, json=[])
        if request.url.params.get("confirm") == refusal.get("confirm") is not None:
            return httpx.Response(200, json={"id": 1, **json.loads(request.content), "realized_gain_usd": None})
        return httpx.Response(409, json=refusal)

    return httpx.Client(base_url="http://server.test", transport=httpx.MockTransport(answer)), seen


def test_seed_ledger_confirms_the_warning_once_with_its_fingerprint():
    c, seen = server()
    assert seed_ledger.seed(c, [ROW]) == 1
    assert seen == ["GET /api/transactions", "POST /api/transactions", "POST /api/transactions?confirm=fp-1"]


def test_seed_ledger_takes_any_other_409_as_a_refusal():
    c, seen = server({"detail": "Not a past-year warning."})
    with pytest.raises(seed_ledger.SeedError, match="refused: 409"):
        seed_ledger.seed(c, [ROW])
    assert seen == ["GET /api/transactions", "POST /api/transactions"]


def test_post_confirmed_returns_a_plain_save_as_it_is():
    def answer(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"id": 5})

    c = httpx.Client(base_url="http://server.test", transport=httpx.MockTransport(answer))
    assert seed_ledger.post_confirmed(c, ROW).json() == {"id": 5}


def test_the_smoke_test_confirms_the_warning_once_with_its_fingerprint():
    c, seen = server()
    assert smoke_test.create(c, **ROW)["id"] == 1
    assert seen == ["POST /api/transactions", "POST /api/transactions?confirm=fp-1"]


def test_the_smoke_test_takes_any_other_409_as_a_failure():
    c, _ = server({"detail": "Not a past-year warning."})
    with pytest.raises(smoke_test.SmokeFailure, match="failed: 409"):
        smoke_test.create(c, **ROW)
