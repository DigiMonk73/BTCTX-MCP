"""
backend/tests/test_ai_rows_same_account_522.py

#522: the AI import's duplicate check took a recorded transaction for a
row when it went the same way (the same source account or the same
destination), so a payout into Exchange BTC beside an identical one
recorded into Wallet was called already recorded and left out: every
deposit comes from External, so the destination was never compared. The
owner's rule (2026-10-18): the AI's rows need the same accounts to be the
same transaction; a different one makes a row only similar, saved unless
removed, its note naming the account. River's rule (#253) stays.
"""

import io
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.models.transaction import Transaction
from backend.services.entry_import import ENTRY_RULE
from backend.services.river_import import STATUS_MATCHED, RiverProposal
from backend.tests.conftest import stub_prices_at

CLIENT = None


@pytest.fixture(autouse=True, scope="module")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _prices(monkeypatch):
    stub_prices_at(monkeypatch, lambda when: 100000)


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


WHEN = "2025-03-20T15:00:00Z"
PAYOUT = {
    "type": "Deposit", "amount": "0.002", "from_account": "External", "to_account": "Wallet",
    "source": "Interest", "cost_basis_usd": "200.00", "date": WHEN,
}
OTHER_BTC = {"Wallet": "Exchange BTC", "Exchange BTC": "Wallet"}


def payout(to_account: str = "Wallet", **changes) -> dict:
    return dict(PAYOUT, to_account=to_account, **changes)


def execute(rows: list[dict]) -> dict:
    out = CLIENT.post("/api/import/entries/execute", json={"rows": rows})
    assert out.status_code == 200, out.text
    return out.json()


def record(row: dict) -> int:
    out = execute([row])
    assert out["imported_count"] == 1, out
    return out["created"][0]["id"]


def preview(rows: list[dict]) -> list[dict]:
    out = CLIENT.post("/api/import/entries/preview", json={"rows": rows})
    assert out.status_code == 200, out.text
    return out.json()["results"]


def ledger() -> list[dict]:
    return CLIENT.get("/api/transactions").json()


def saved_after(known: set[int]) -> list[dict]:
    return [tx for tx in ledger() if tx["id"] not in known]


@pytest.mark.parametrize("recorded_into", ["Wallet", "Exchange BTC"])
def test_a_payout_into_the_other_bitcoin_account_is_saved_flagged_with_the_account(recorded_into):
    """#522's steps: a payout recorded into one BTC account, the same payout
    (type, amount, source, minute) into the other: a possible duplicate
    naming the account, saved; on develop a duplicate, left out."""
    sent_into = OTHER_BTC[recorded_into]
    recorded = record(payout(recorded_into))
    [result] = preview([payout(sent_into)])
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", recorded)
    assert f"the same minute; recorded into {recorded_into}, not {sent_into}" in result["warnings"][0]
    assert result["warnings"][0].endswith("Saved unless you remove it.")
    out = execute([payout(sent_into)])
    assert out["imported_count"] == 1, out
    [new] = saved_after({recorded})
    assert new["to_account_id"] == (4 if sent_into == "Exchange BTC" else 2)


def test_a_date_alone_into_the_other_account_is_saved_flagged_with_the_account():
    """The same for a row given as a date alone: that day, another account."""
    recorded = record(payout("Wallet"))
    row = payout("Exchange BTC", date=WHEN[:10])
    [result] = preview([row])
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", recorded)
    assert "the same day; recorded into Wallet, not Exchange BTC" in result["warnings"][0]
    assert execute([row])["imported_count"] == 1


@pytest.mark.parametrize("account", ["Wallet", "Exchange BTC"])
def test_the_same_payout_into_the_same_account_is_still_left_out(account):
    recorded = record(payout(account))
    [result] = preview([payout(account)])
    assert (result["status"], result["matched_transaction_id"]) == ("duplicate", recorded)
    assert "the same type, accounts, BTC amount" in result["warnings"][0]
    assert execute([payout(account)])["imported_count"] == 0
    assert len(ledger()) == 1


def test_a_resend_saves_nothing():
    """Saved once into the other account, the row sent again is that payout."""
    recorded = record(payout("Wallet"))
    assert execute([payout("Exchange BTC")])["imported_count"] == 1
    [saved] = saved_after({recorded})
    [result] = preview([payout("Exchange BTC")])
    assert (result["status"], result["matched_transaction_id"]) == ("duplicate", saved["id"])
    assert execute([payout("Exchange BTC")])["imported_count"] == 0
    assert len(ledger()) == 2


@pytest.mark.parametrize("wallet_first", [True, False], ids=["wallet row first", "exchange row first"])
def test_both_payouts_in_one_request_each_find_their_own_account(wallet_first):
    """The Wallet payout recorded; a request with it and the Exchange BTC one
    saves the Exchange BTC one, in either order (on develop, the Exchange BTC
    row sent first took the Wallet payout, and a second Wallet payout was
    saved in its place). Sent again, nothing more."""
    recorded = record(payout("Wallet"))
    rows = [payout("Wallet"), payout("Exchange BTC")]
    rows = rows if wallet_first else rows[::-1]
    statuses = {r["row"]: (r["status"], r["matched_transaction_id"]) for r in preview(rows)}
    wallet_row, exchange_row = (1, 2) if wallet_first else (2, 1)
    assert statuses[wallet_row] == ("duplicate", recorded)
    assert statuses[exchange_row] == ("ready", None)
    assert execute(rows)["imported_count"] == 1
    [new] = saved_after({recorded})
    assert new["to_account_id"] == 4
    assert execute(rows)["imported_count"] == 0
    assert len(ledger()) == 2


def own_btc_in_both_accounts() -> set[int]:
    """Bitcoin in the wallet and on the exchange, a year before WHEN (a
    month apart, so neither is the other's duplicate on develop)."""
    return {
        record(dict(PAYOUT, source="MyBTC", amount="0.1", cost_basis_usd="1000.00", date=date, to_account=account))
        for account, date in (("Wallet", "2024-03-01T12:00:00Z"), ("Exchange BTC", "2024-04-01T12:00:00Z"))
    }


def test_a_spend_from_the_other_bitcoin_account_is_saved_flagged_with_the_account():
    known = own_btc_in_both_accounts()
    spend = {"type": "Withdrawal", "amount": "0.002", "from_account": "Wallet", "to_account": "External",
             "purpose": "Spent", "proceeds_usd": "200.00", "date": WHEN}
    known.add(record(spend))
    other = dict(spend, from_account="Exchange BTC")
    [result] = preview([other])
    assert result["status"] == "possible_duplicate", result
    assert "recorded from Wallet, not Exchange BTC" in result["warnings"][0]
    assert execute([other])["imported_count"] == 1
    [new] = saved_after(known)
    assert new["from_account_id"] == 4


def test_a_buy_paid_from_the_other_dollar_account_is_saved_flagged_with_the_account():
    buy = {"type": "Buy", "amount": "0.002", "from_account": "Bank", "to_account": "Exchange BTC",
           "cost_basis_usd": "200.00", "date": WHEN}
    recorded = record(buy)
    other = dict(buy, from_account="Exchange USD")
    [result] = preview([other])
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", recorded), result
    assert "recorded from Bank, not Exchange USD" in result["warnings"][0]
    assert execute([other])["imported_count"] == 1
    [new] = saved_after({recorded})
    assert new["from_account_id"] == 3


def test_a_move_to_the_exchange_beside_a_consolidation_in_the_wallet_is_saved_flagged():
    """Both leave Wallet, so they went the same way: a move to Exchange BTC
    and a consolidation (Wallet to Wallet) of the same amount, fee and
    minute were one transaction on develop."""
    known = own_btc_in_both_accounts()
    consolidation = {"type": "Transfer", "amount": "0.002", "from_account": "Wallet", "to_account": "Wallet",
                     "fee_amount": "0.00001", "fee_currency": "BTC", "date": WHEN}
    known.add(record(consolidation))
    move = dict(consolidation, to_account="Exchange BTC")
    [result] = preview([move])
    assert result["status"] == "possible_duplicate", result
    assert "recorded into Wallet, not Exchange BTC" in result["warnings"][0]
    assert execute([move])["imported_count"] == 1
    [new] = saved_after(known)
    assert (new["from_account_id"], new["to_account_id"]) == (2, 4)
    assert execute([move])["imported_count"] == 0


def test_a_dollar_deposit_into_the_other_dollar_account_is_saved_flagged():
    pay = {"type": "Deposit", "amount": "500", "from_account": "External", "to_account": "Bank",
           "source": "Income", "date": WHEN}
    recorded = record(pay)
    other = dict(pay, to_account="Exchange USD")
    [result] = preview([other])
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", recorded), result
    assert "recorded into Bank, not Exchange USD" in result["warnings"][0]
    assert execute([other])["imported_count"] == 1
    [new] = saved_after({recorded})
    assert new["to_account_id"] == 3


def test_a_stored_transaction_without_an_account_is_named_so():
    """A transaction's accounts may be blank in the database (the columns
    allow it): the note says so rather than failing the preview."""
    row = RiverProposal(
        row_number=1, timestamp=datetime(2025, 3, 20, 15, tzinfo=timezone.utc), river_tag=None, type="Deposit",
        from_account_id=99, to_account_id=4, amount=Decimal("0.002"), source="Interest",
    )
    tx = Transaction(type="Deposit", from_account_id=99, to_account_id=None, amount=Decimal("0.002"),
                     source="Interest")
    assert ENTRY_RULE.differences(row, tx) == ["recorded into no account, not Exchange BTC"]


def test_a_row_into_the_other_account_beside_a_named_row_is_not_unclear():
    """#497's check: a named row beside a row without a name is unclear only
    when the named transaction could be that row too. A row into the other
    account can't be the Wallet payout: both are saved, and sent again,
    nothing more."""
    recorded = record(payout("Wallet"))
    rows = [payout("Wallet", not_a_duplicate_of=recorded), payout("Exchange BTC")]
    results = preview(rows)
    assert [r["status"] for r in results] == ["ready", "ready"], results
    assert execute(rows)["imported_count"] == 2
    assert sorted(tx["to_account_id"] for tx in saved_after({recorded})) == [2, 4]
    assert execute(rows)["imported_count"] == 0
    assert len(ledger()) == 3


def test_a_row_named_as_the_other_accounts_payout_is_saved_once():
    """A preview before this fix called the Exchange BTC payout the Wallet
    one, so the AI may send it named as that one (not_a_duplicate_of). That
    name counts for nothing now (it isn't a duplicate of the row): the row
    is saved, flagged; sent again, it's left out."""
    recorded = record(payout("Wallet"))
    row = payout("Exchange BTC", not_a_duplicate_of=recorded)
    [result] = preview([row])
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", recorded)
    assert execute([row])["imported_count"] == 1
    [saved] = saved_after({recorded})
    [result] = preview([row])
    assert (result["status"], result["matched_transaction_id"]) == ("duplicate", saved["id"])
    assert f"not_a_duplicate_of names tx #{recorded}, which isn't a duplicate of this row" in result["warnings"][0]
    assert execute([row])["imported_count"] == 0
    assert len(ledger()) == 2


# River's rule is unchanged (#253): its rows compare no account.
RIVER_HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"


def test_river_still_finds_a_payout_recorded_into_the_wallet():
    """River's Interest row goes into Exchange BTC; the same payout recorded
    into Wallet (moved there by the owner, or entered so) is still that row."""
    recorded = record(payout("Wallet"))
    csv = f"{RIVER_HEADER}\n2025-03-20 15:00:00,,,0.00200000,BTC,,,Interest\n".encode()
    out = CLIENT.post("/api/import/river/preview", files={"file": ("river.csv", io.BytesIO(csv), "text/csv")})
    assert out.status_code == 200, out.text
    [proposal] = out.json()["proposals"]
    assert proposal["to_account"] == "Exchange BTC"
    assert (proposal["status"], proposal["matched_tx_id"]) == (STATUS_MATCHED, recorded)
