"""
#581: the duplicate checks of the AI connector's preview and River's import
compared amounts as bare numbers, without their currency
(river_import.annotate_duplicates). A River payout of 0.01 BTC at the same
minute as a recorded $0.01 deposit was "In ledger" and left out unless
ticked, its income missing; the AI's preview flagged a dollar row of a
near amount, and a dollar row beside a bitcoin one. A row matches, or is
called similar to, only a transaction of its own currency (bitcoin with
bitcoin, dollars with dollars), in every pass; the near-amount pass is for
bitcoin moves only (a network fee makes a hand-typed one approximate).
Every bitcoin and every dollar match within a currency stays as it was.

All rows are synthetic.
"""

import io

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


# The AI connector's rows (/api/import/entries)

def execute(client, rows: list[dict]) -> list[int]:
    r = client.post("/api/import/entries/execute", json={"rows": rows})
    assert r.status_code == 200, r.text
    return [tx["id"] for tx in r.json()["created"]]


def preview(client, row: dict) -> dict:
    r = client.post("/api/import/entries/preview", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [result] = r.json()["results"]
    return result


def not_flagged(result: dict) -> None:
    """Saved as a new row: no duplicate, no possible duplicate, no note naming a transaction."""
    assert result["status"] == "ready", result
    assert result["matched_transaction_id"] is None, result
    assert not any("tx #" in w for w in result["warnings"]), result["warnings"]


BANK_FUNDS = {
    "date": "2025-03-01T15:00:00Z", "type": "Deposit", "amount": "5000",
    "from_account": "External", "to_account": "Bank", "source": "MyBTC",
}
WALLET_FUNDS = {
    "date": "2025-03-01T15:00:00Z", "type": "Deposit", "amount": "1",
    "from_account": "External", "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "50000.00",
}
RENT = {
    "date": "2025-03-20T15:00:00Z", "type": "Withdrawal", "amount": "1500",
    "from_account": "Bank", "to_account": "External",
}
TO_EXCHANGE = {
    "date": "2025-03-20T15:00:00Z", "type": "Transfer", "amount": "1000",
    "from_account": "Bank", "to_account": "Exchange USD",
}
SPEND = {
    "date": "2025-03-20T15:00:00Z", "type": "Withdrawal", "amount": "0.45",
    "from_account": "Wallet", "to_account": "External", "purpose": "Gift",
}


def test_a_dollar_withdrawal_of_a_near_amount_is_not_flagged(client):
    """The issue's case: $1,250 three hours after a recorded $1,500 was
    "Likely the same event as tx #2 (Withdrawal $1,500.00)"."""
    execute(client, [BANK_FUNDS, RENT])
    not_flagged(preview(client, dict(RENT, date="2025-03-20T18:00:00Z", amount="1250")))


def test_a_dollar_transfer_of_a_near_amount_is_not_flagged(client):
    """$900 Bank -> Exchange USD beside a recorded $1,000 one."""
    execute(client, [BANK_FUNDS, TO_EXCHANGE])
    not_flagged(preview(client, dict(TO_EXCHANGE, date="2025-03-20T18:00:00Z", amount="900")))


def test_a_dollar_withdrawal_is_not_like_a_bitcoin_one_of_a_near_number(client):
    """$0.50 Bank -> External beside a recorded 0.45 BTC Wallet -> External
    (the same destination was all _compatible asked)."""
    execute(client, [BANK_FUNDS, WALLET_FUNDS, SPEND])
    not_flagged(preview(client, dict(RENT, date="2025-03-20T18:00:00Z", amount="0.50")))


def test_a_dollar_withdrawal_is_not_like_a_bitcoin_one_of_the_same_number(client):
    """The same-amount pass too: $0.45 was "Same BTC amount as tx #3"."""
    execute(client, [BANK_FUNDS, WALLET_FUNDS, SPEND])
    not_flagged(preview(client, dict(RENT, date="2025-03-20T18:00:00Z", amount="0.45")))


def test_a_bitcoin_withdrawal_of_a_near_amount_is_still_flagged(client):
    """Unchanged: a bitcoin move typed by hand, its fee guessed, is approximate."""
    _btc, recorded = execute(client, [WALLET_FUNDS, dict(SPEND, amount="0.5")])
    result = preview(client, dict(SPEND, date="2025-03-20T18:00:00Z"))
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", recorded)
    assert f"Likely the same event as tx #{recorded} (Withdrawal 0.50000000 BTC) recorded with a different " \
           "amount. Saved unless you remove it." in result["warnings"]


def test_a_dollar_withdrawal_of_the_same_amount_is_still_flagged(client):
    """Unchanged: the same dollars within 48 hours is similar."""
    _funds, recorded = execute(client, [BANK_FUNDS, RENT])
    result = preview(client, dict(RENT, date="2025-03-20T18:00:00Z"))
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", recorded)
    assert any(w.startswith(f"Same dollar amount as tx #{recorded} (Withdrawal $1,500.00), recorded 3 hours "
                            "earlier") for w in result["warnings"]), result["warnings"]


def test_a_dollar_row_already_recorded_is_still_a_duplicate(client):
    """Unchanged: the same dollars, minute and kind is left out."""
    _funds, recorded = execute(client, [BANK_FUNDS, RENT])
    result = preview(client, RENT)
    assert (result["status"], result["matched_transaction_id"]) == ("duplicate", recorded)
    r = client.post("/api/import/entries/execute", json={"rows": [RENT]})
    assert r.status_code == 200 and r.json()["skipped_duplicates"] == 1, r.text


# River's import (/api/import/river)

RIVER_HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"
PAYOUT = "2026-02-01 09:00:00,,,0.01000000,BTC,,,Interest"


def river_preview(client, rows: list[str]) -> list[dict]:
    content = ("\n".join([RIVER_HEADER, *rows]) + "\n").encode()
    r = client.post("/api/import/river/preview", files={"file": ("river.csv", io.BytesIO(content), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()["proposals"]


def record(client, when: str, amount: str, to_account_id: int, **fields) -> int:
    """A recorded deposit from External (1 Bank: dollars; 4 Exchange BTC: bitcoin)."""
    r = client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": when, "from_account_id": 99, "to_account_id": to_account_id,
        "amount": amount, "fee_amount": "0", "fee_currency": "USD" if to_account_id == 1 else "BTC", **fields,
    })
    assert r.is_success, r.text
    return r.json()["id"]


def dollar_deposit(client, when: str, amount: str) -> int:
    return record(client, when, amount, 1, source="Income")


def bitcoin_payout(client, when: str, amount: str) -> int:
    return record(client, when, amount, 4, source="Interest", cost_basis_usd="1000.00")


def test_a_river_payout_beside_a_dollar_deposit_of_the_same_number_is_new(client):
    """The issue's case: 0.01 BTC of Interest at the minute of a recorded
    $0.01 deposit was "In ledger", unticked: its income left out. It's new,
    ticked, and imported."""
    dollar_deposit(client, "2026-02-01T09:00:00Z", "0.01")
    [payout] = river_preview(client, [PAYOUT])
    assert (payout["status"], payout["matched_tx_id"]) == ("new", None), payout
    keys = ("date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd",
            "fee_amount", "fee_currency", "source", "purpose")
    r = client.post("/api/import/river/execute", json={"rows": [{k: payout[k] for k in keys}]})
    assert r.status_code == 200 and r.json()["imported_count"] == 1, r.text


def test_a_river_payout_a_day_after_a_dollar_deposit_of_the_same_number_is_not_to_review(client):
    """0.5 BTC 23 hours after a recorded $0.50 deposit was "Review": "Same
    dollar amount as tx #1 (Deposit $0.50)"."""
    dollar_deposit(client, "2026-02-01T10:00:00Z", "0.50")
    [payout] = river_preview(client, ["2026-02-02 09:00:00,,,0.50000000,BTC,,,Interest"])
    assert (payout["status"], payout["matched_tx_id"], payout["discrepancy"]) == ("new", None, None), payout


def test_a_river_payout_beside_both_is_its_bitcoin_copy(client):
    """A dollar deposit of the same number nearer in time never takes the
    match from the payout's own bitcoin copy."""
    dollar_deposit(client, "2026-02-01T09:00:00Z", "0.01")
    recorded = bitcoin_payout(client, "2026-02-01T09:00:30Z", "0.01")
    [payout] = river_preview(client, [PAYOUT])
    assert (payout["status"], payout["matched_tx_id"]) == ("matched", recorded), payout


def test_a_river_payout_already_recorded_is_still_in_the_ledger(client):
    """Unchanged: River's rule, the same kind, bitcoin amount and minute."""
    recorded = bitcoin_payout(client, "2026-02-01T09:00:40Z", "0.01")
    [payout] = river_preview(client, [PAYOUT])
    assert (payout["status"], payout["matched_tx_id"]) == ("matched", recorded), payout


def test_a_river_send_of_a_near_amount_is_still_to_review_unticked(client):
    """Unchanged: a send beside a hand-typed transfer about 3 % off."""
    bitcoin_payout(client, "2026-01-01T12:00:00Z", "0.01")
    r = client.post("/api/transactions", json={
        "type": "Transfer", "timestamp": "2026-02-15T08:00:00Z", "from_account_id": 4, "to_account_id": 2,
        "amount": "0.00103000", "fee_amount": "0.00000500", "fee_currency": "BTC",
    })
    assert r.is_success, r.text
    [send] = river_preview(client, ["2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,"])
    assert (send["status"], send["matched_tx_id"], send["near_amount"]) == ("discrepancy", r.json()["id"], True)
