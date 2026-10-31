"""
An exchange's 1099-DA answer given when it's added (#708): Settings' Add
form asks whether the exchange sends a Form 1099-DA, so the answer is saved
with the exchange, before any of its sales. Left out, the switch is on, the
owner's default (2.0 spec 5.9); a bank or a wallet has no such setting.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.exchange import Exchange
from backend.services.account import NO_1099DA
from backend.tests.conftest import default_login
from backend.tests.two_exchanges import BANK, Ledger

URL = "/api/accounts/"
ABROAD_USD, ABROAD_BTC = 100, 101  # the ids a fresh ledger's first new exchange gets


@pytest.fixture
def client(fresh_app) -> TestClient:
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    return c


def _switch_saved(Session, name: str) -> list[bool]:
    with Session() as db:
        return [on for (on,) in db.query(Exchange.sends_1099da).filter(Exchange.name == name)]


@pytest.mark.parametrize("sent, saved", [(False, False), (True, True), (None, True)])
def test_an_exchange_is_added_with_its_answer_or_on_by_default(client, fresh_app, sent, saved):
    body = {"kind": "exchange", "name": "Abroad"} | ({} if sent is None else {"sends_1099da": sent})
    r = client.post(URL, json=body)
    assert r.status_code == 201, r.text
    assert [(a["id"], a["sends_1099da"]) for a in r.json()] == [(ABROAD_USD, saved), (ABROAD_BTC, saved)]
    assert _switch_saved(fresh_app, "Abroad") == [saved]


@pytest.mark.parametrize("kind", ["bank", "wallet"])
@pytest.mark.parametrize("sent", [True, False])
def test_a_bank_or_a_wallet_has_no_1099da_answer(client, kind, sent):
    before = client.get(URL).json()
    r = client.post(URL, json={"kind": kind, "name": "Second", "sends_1099da": sent})
    assert (r.status_code, r.json()["detail"]) == (400, NO_1099DA)
    assert client.get(URL).json() == before


def test_a_null_answer_is_none_given(client):
    r = client.post(URL, json={"kind": "wallet", "name": "Jade", "sends_1099da": None})
    assert r.status_code == 201, r.text
    assert r.json()[0]["sends_1099da"] is None


def _sales_on_abroad(ledger: Ledger) -> tuple[list[str], list[str]]:
    """A lot bought in 2024 and one in 2026, sold in 2025 and 2026: each
    year's boxes, once the app's rows and the second calculation's agree."""
    ledger.save("Buy", "2024-01-10", BANK, ABROAD_BTC, "1.00000000", cost_basis_usd="40000.00")
    ledger.save("Buy", "2026-02-01", BANK, ABROAD_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Sell", "2025-03-01", ABROAD_BTC, ABROAD_USD, "0.50000000", gross_proceeds_usd="45000.00")
    ledger.save("Sell", "2026-06-01", ABROAD_BTC, ABROAD_USD, "1.00000000", gross_proceeds_usd="90000.00")
    for year in (2025, 2026):
        assert ledger.form_8949(year) == ledger.independent_form_8949(year)
    return ledger.boxes(2025), ledger.boxes(2026)


@pytest.mark.parametrize("sent, boxes", [
    (False, (["L"], ["I", "L"])),       # on no broker form
    (True, (["K"], ["G", "K"])),        # as before #708: the 1099-DA's boxes
    (None, (["K"], ["G", "K"])),
])
def test_an_exchange_added_with_its_answer_puts_its_sales_in_that_answers_boxes(client, fresh_app, sent, boxes):
    body = {"kind": "exchange", "name": "Abroad"} | ({} if sent is None else {"sends_1099da": sent})
    assert client.post(URL, json=body).status_code == 201
    assert _sales_on_abroad(Ledger(client, fresh_app)) == boxes
