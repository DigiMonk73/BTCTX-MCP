"""
#525: when the AI connector's preview flagged a dollar row as a possible
duplicate, its note called the dollars bitcoin: "Same BTC amount as tx #1
(Deposit 500.00000000 BTC)" for a $500 deposit. The note is River's
(river_import._match_similar, and _match_roughly's "Likely the same
event"), whose file has no dollar rows. A dollar transaction's amount is
said as dollars; a bitcoin one's as before. The warning for a row already
recorded said "the same type, accounts, BTC amount" for a dollar row too
(#579's review): it says "dollar amount". Only the words: each row is
flagged, saved or left out as it was.

All rows are synthetic.
"""

import pytest

from backend.tests.conftest import stub_daily_prices


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture
def client(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield auth_client
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def execute(client, rows: list[dict]) -> list[int]:
    r = client.post("/api/import/entries/execute", json={"rows": rows})
    assert r.status_code == 200, r.text
    return [tx["id"] for tx in r.json()["created"]]


def flagged(client, row: dict) -> dict:
    r = client.post("/api/import/entries/preview", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [result] = r.json()["results"]
    assert result["status"] == "possible_duplicate", result
    return result


INCOME = {
    "date": "2025-03-20T15:00:00Z", "type": "Deposit", "amount": "500",
    "from_account": "External", "to_account": "Bank", "source": "Income",
}
BANK_FUNDS = dict(INCOME, date="2025-03-01T15:00:00Z", amount="2000", source="MyBTC")
RENT = {
    "date": "2025-03-20T15:00:00Z", "type": "Withdrawal", "amount": "1500",
    "from_account": "Bank", "to_account": "External",
}


def test_a_dollar_deposit_of_the_same_amount_is_said_in_dollars(client):
    """The issue's reproduction: $500 of Income, then $500 of Interest 18 hours later."""
    [recorded] = execute(client, [INCOME])
    result = flagged(client, dict(INCOME, date="2025-03-21T09:00:00Z", source="Interest"))
    assert result["matched_transaction_id"] == recorded
    assert f"Same dollar amount as tx #{recorded} (Deposit $500.00), recorded 18 hours earlier; " \
           "its source is Income, not Interest: it may be the same transaction. Saved unless you remove it." \
           in result["warnings"]


def test_a_dollar_withdrawal_of_a_near_amount_is_said_in_dollars(client):
    """_match_roughly's note: $1,450 beside a recorded $1,500, 3 hours apart."""
    _funds, recorded = execute(client, [BANK_FUNDS, RENT])
    result = flagged(client, dict(RENT, date="2025-03-20T18:00:00Z", amount="1450"))
    assert result["matched_transaction_id"] == recorded
    assert f"Likely the same event as tx #{recorded} (Withdrawal $1,500.00) recorded with a different amount. " \
           "Saved unless you remove it." in result["warnings"]


def preview(client, row: dict) -> dict:
    r = client.post("/api/import/entries/preview", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [result] = r.json()["results"]
    return result


def test_a_dollar_row_already_recorded_is_said_in_dollars(client):
    """The review's reproduction: a recorded $1,500 deposit sent again."""
    row = dict(INCOME, amount="1500")
    [recorded] = execute(client, [row])
    result = preview(client, row)
    assert (result["status"], result["matched_transaction_id"]) == ("duplicate", recorded)
    assert result["warnings"] == [
        f"Already recorded as tx #{recorded} (the same type, accounts, dollar amount, source or purpose, a "
        f"Buy's cost basis, and time): left out. If the user says it's another transaction, send it with "
        f"not_a_duplicate_of: {recorded}."
    ]


def test_a_bitcoin_row_already_recorded_keeps_its_words(client):
    payout = dict(INCOME, to_account="Wallet", amount="0.002", cost_basis_usd="200.00")
    [recorded] = execute(client, [payout])
    result = preview(client, payout)
    assert result["status"] == "duplicate"
    assert result["warnings"][0].startswith(f"Already recorded as tx #{recorded} (the same type, accounts, BTC amount,")


def test_a_bitcoin_row_keeps_its_bitcoin_note(client):
    """The same note for bitcoin, unchanged: River's preview shows it too."""
    payout = dict(INCOME, to_account="Wallet", amount="0.002", cost_basis_usd="200.00")
    [recorded] = execute(client, [payout])
    result = flagged(client, dict(payout, date="2025-03-21T09:00:00Z", source="Interest"))
    assert f"Same BTC amount as tx #{recorded} (Deposit 0.00200000 BTC), recorded 18 hours earlier; " \
           "its source is Income, not Interest: it may be the same transaction. Saved unless you remove it." \
           in result["warnings"]
