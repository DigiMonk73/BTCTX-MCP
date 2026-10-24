"""
A connector older than 2.0 can't tell a second wallet or exchange from the
first (2.0 spec 5.12; card B7a #354): its guide puts a second wallet's coins
in Wallet, which the server can't tell from a real Wallet entry. So once the
ledger has more than one wallet or more than one exchange (hidden ones
counted, so hiding one doesn't let it lump into the other), the AI key's
writes (an import, an edit, a delete, Recalculate Ledger) are refused with a
409 unless the request says it comes from a 2.0 connector
(X-BitcoinTX-Connector, which a 1.x connector never sends). Its reads keep
working, nothing it sent is saved, and a login's writes are never asked. The
header isn't a security check: the AI key and its routes are.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.transaction import Transaction
from backend.tests.conftest import default_login

# 5.12's words, exactly
OLD_CONNECTOR = ("This AI connector is older than BitcoinTX 2.0 and can't tell your wallets or exchanges apart. "
                 "Update it (btctx-mcp 2.0 or later), then try again.")
DEPOSIT = {"date": "2026-01-10T12:00:00Z", "type": "Deposit", "amount": "0.01", "from_account": "External",
           "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "900"}


class Ledger:
    """A fresh install: the owner logged in, and the AI key's own client
    (a 1.x connector's requests: no X-BitcoinTX-Connector)."""

    def __init__(self, Session):
        self.Session = Session
        self.owner = TestClient(app)
        assert self.owner.post("/api/login", json=default_login()).status_code == 200
        assert self.owner.put("/api/settings/ai-access", json={"on": True}).status_code == 200
        key = self.owner.post("/api/settings/ai-key").json()["key"]
        self.ai = TestClient(app, headers={"Authorization": f"Bearer {key}"})
        r = self.owner.post("/api/transactions", json={
            "type": "Deposit", "timestamp": "2026-01-05T12:00:00Z", "from_account_id": 99, "to_account_id": 2,
            "amount": "0.5", "fee_amount": "0", "fee_currency": "BTC", "source": "MyBTC", "cost_basis_usd": "45000"})
        assert r.status_code == 200, r.text
        self.first = r.json()["id"]

    def add(self, kind: str, name: str) -> list[dict]:
        r = self.owner.post("/api/accounts/", json={"kind": kind, "name": name})
        assert r.status_code == 201, r.text
        return r.json()

    def rows(self) -> int:
        with self.Session() as db:
            return db.query(Transaction).count()

    def writes(self, headers: dict | None = None) -> list:
        """The AI key's four writes, each an answer."""
        h = headers or {}
        return [
            self.ai.post("/api/import/entries/execute", json={"rows": [DEPOSIT]}, headers=h),
            self.ai.put(f"/api/transactions/{self.first}", json={"amount": "0.4"}, headers=h),
            self.ai.delete(f"/api/transactions/{self.first}", headers=h),
            self.ai.post("/api/transactions/recalculate", headers=h),
        ]


@pytest.fixture
def ledger(fresh_app) -> Ledger:
    return Ledger(fresh_app)


def test_with_one_of_each_an_old_connector_writes_as_it_did(ledger):
    """1.x unchanged: one wallet and one exchange, nothing asked."""
    ledger.add("bank", "Credit Union")  # a second bank: dollars, no basis to mix up
    answers = ledger.writes()
    assert [r.status_code for r in answers] == [200, 200, 204, 200], [r.text for r in answers]


@pytest.mark.parametrize("kind, name", [("wallet", "Cold Storage"), ("exchange", "Kraken")])
def test_with_a_second_wallet_or_exchange_its_writes_are_refused(ledger, kind, name):
    ledger.add(kind, name)
    before = ledger.rows()
    for r in ledger.writes():
        assert (r.status_code, r.json()["detail"]) == (409, OLD_CONNECTOR), r.request.url
    assert ledger.rows() == before
    with ledger.Session() as db:
        assert str(db.get(Transaction, ledger.first).amount) == "0.50000000"  # the edit wasn't saved


def test_a_hidden_second_wallet_still_counts(ledger):
    [cold] = ledger.add("wallet", "Cold Storage")
    assert ledger.owner.put(f"/api/accounts/{cold['id']}", json={"hidden": True}).status_code == 200
    assert {r.status_code for r in ledger.writes()} == {409}


def test_an_old_connectors_reads_still_work(ledger):
    ledger.add("wallet", "Cold Storage")
    for path in ("/api/transactions", f"/api/transactions/{ledger.first}", "/api/accounts/",
                 "/api/calculations/accounts/balances", "/api/review"):
        assert ledger.ai.get(path).status_code == 200, path
    preview = ledger.ai.post("/api/import/entries/preview", json={"rows": [DEPOSIT]})
    assert preview.status_code == 200 and preview.json()["results"][0]["status"] == "ready", preview.text
    assert ledger.ai.post("/api/backup/ai-copy").status_code == 200  # a copy changes no figure
    assert ledger.rows() == 1


@pytest.mark.parametrize("version", ["2.0.0", "2.0.0b1", "1.2.10", "unknown"])
def test_a_2_0_connectors_writes_go_through(ledger, version):
    """Any version a 2.0 connector says: 1.2.10 until B10a bumps it, unknown
    from a source tree, a beta's (B5a's note on #350). A 1.x one says none."""
    ledger.add("wallet", "Cold Storage")
    answers = ledger.writes({"X-BitcoinTX-Connector": version})
    assert [r.status_code for r in answers] == [200, 200, 204, 200], [r.text for r in answers]


def test_the_owners_writes_are_never_asked(ledger):
    ledger.add("wallet", "Cold Storage")
    ledger.add("exchange", "Kraken")
    r = ledger.owner.put(f"/api/transactions/{ledger.first}", json={"amount": "0.4"})
    assert r.status_code == 200, r.text
    assert ledger.owner.post("/api/transactions/recalculate").status_code == 200


def test_every_route_the_key_changes_the_ledger_on_is_a_write_here():
    """The AI key's routes that aren't reads, but the preview's dry run and
    the AI copy, which change no figure: so a renamed route can't slip out."""
    from backend.services import ai_key

    not_reads = {(method, route) for method, route, _ in ai_key.AI_KEY_ROUTES if method != "GET"}
    assert ai_key.WRITES == not_reads - {("POST", "/api/import/entries/preview"), ("POST", "/api/backup/ai-copy")}
