"""
A file's row already recorded in another account of the same kind (#707).
1.x kept one exchange and one wallet, and its guide had a second
exchange's trades recorded in them ("pooled"). In 2.0 that exchange is
added and its file imported into it: the owner's rule of 2026-10-15 never
takes a transaction naming another exchange (or wallet) on the same side
for a row's copy, so each pooled trade would be saved a second time,
unflagged. The owner's decision (2026-10-25): a row of the same kind,
bitcoin amount and minute as a transaction in another account of the same
kind is similar (Review, ticked, never left out by itself), its note naming
that account. The exact pass keeps to the row's own account, and the AI's
rows keep their own rule.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.river_import import RiverProposal, annotate_duplicates
from backend.tests.account_pairs import add_them
from backend.tests.conftest import default_login, stub_daily_prices, stub_prices_at

HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"
WHEN, AT = "2026-04-07 10:00:00", "2026-04-07T10:00:00Z"
BUY = f"{WHEN},1500.00,USD,0.03000000,BTC,,,Buy"
SELL = f"{WHEN},0.00500000,BTC,500.00,USD,5.00,USD,Sell"
SEND = f"{WHEN},0.00100000,BTC,,,0.00000500,BTC,"  # its Transfer's amount: 0.001005 with its fee
RECEIVE = f"{WHEN},,,0.00060000,BTC,,,"
PAYOUT = f"{WHEN},,,0.00002000,BTC,,,Interest"
BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99
COLD, CREDIT_UNION, KRAKEN_USD, KRAKEN_BTC = 100, 101, 102, 103


@pytest.fixture
def client(fresh_app, monkeypatch) -> TestClient:
    """A 1.x ledger's accounts and a second wallet, bank and exchange
    (account_pairs' ids), each bitcoin account holding coins to record from."""
    stub_daily_prices(monkeypatch, lambda day: 100000.0)
    stub_prices_at(monkeypatch, lambda when: 100000)
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    add_them(client)
    for account in (EXCHANGE_BTC, KRAKEN_BTC, WALLET, COLD):
        record(client, "Deposit", EXTERNAL, account, "1", at="2026-01-01T12:00:00Z", source="MyBTC",
               cost_basis_usd="1")
    return client


def record(client: TestClient, tx_type: str, from_id: int, to_id: int, amount: str, at: str = AT, **more) -> int:
    r = client.post("/api/transactions", json={"type": tx_type, "timestamp": at, "from_account_id": from_id,
                                               "to_account_id": to_id, "amount": amount, **more})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def into_kraken(client: TestClient, *rows: str, wallet: int = WALLET) -> list[dict]:
    """The rows' preview, as the file of the exchange added in 2.0 (Kraken)."""
    content = ("\n".join([HEADER, *rows]) + "\n").encode()
    r = client.post("/api/import/river/preview", files={"file": ("kraken.csv", content, "text/csv")},
                    data={"exchange_account_id": str(KRAKEN_BTC), "wallet_account_id": str(wallet)})
    assert r.status_code == 200, r.text
    return r.json()["proposals"]


def found(proposal: dict) -> tuple:
    return proposal["status"], proposal["matched_tx_id"], proposal["near_amount"]


# The pooled trades: recorded in Exchange, the file's into Kraken
def test_a_buy_recorded_in_another_exchange_is_marked_review(client):
    """T3's case on #707: imported a second time, unflagged, before."""
    tx = record(client, "Buy", BANK, EXCHANGE_BTC, "0.03", cost_basis_usd="1500")
    [buy] = into_kraken(client, BUY)
    assert found(buy) == ("discrepancy", tx, False)  # ticked: imported unless the owner unticks it
    assert buy["discrepancy"] == (
        f"Same BTC amount as tx #{tx} (Buy 0.03000000 BTC), the same minute; recorded into Exchange BTC, not "
        "Kraken BTC: it may already be recorded in Exchange")


def test_a_buy_paid_from_the_exchanges_dollars_is_marked_too(client):
    """Bank beside Exchange USD is the funding River never names; the coins
    went into another exchange's BTC account."""
    record(client, "Deposit", EXTERNAL, EXCHANGE_USD, "2000", at="2026-01-01T12:00:00Z")
    tx = record(client, "Buy", EXCHANGE_USD, EXCHANGE_BTC, "0.03", cost_basis_usd="1500")
    [buy] = into_kraken(client, BUY)
    assert found(buy) == ("discrepancy", tx, False)


def test_a_sell_recorded_in_another_exchange_names_both_its_accounts(client):
    tx = record(client, "Sell", EXCHANGE_BTC, EXCHANGE_USD, "0.005", proceeds_usd="505", fee_amount="5",
                fee_currency="USD")
    [sell] = into_kraken(client, SELL)
    assert found(sell) == ("discrepancy", tx, False)
    assert sell["discrepancy"] == (
        f"Same BTC amount as tx #{tx} (Sell 0.00500000 BTC), the same minute; recorded from Exchange BTC, not "
        "Kraken BTC; recorded into Exchange USD, not Kraken USD: it may already be recorded in Exchange")


def test_a_send_from_another_exchange_is_marked_review(client):
    tx = record(client, "Transfer", EXCHANGE_BTC, WALLET, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    [send] = into_kraken(client, SEND)
    assert found(send) == ("discrepancy", tx, False)
    assert "recorded from Exchange BTC, not Kraken BTC: it may already be recorded in Exchange" in send["discrepancy"]


def test_a_send_from_another_exchange_into_another_wallet_names_both(client):
    """1.x's pooled send, from Exchange into its one Wallet, beside the file's
    into the wallet chosen for it (Cold Storage)."""
    tx = record(client, "Transfer", EXCHANGE_BTC, WALLET, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    [send] = into_kraken(client, SEND, wallet=COLD)
    assert found(send) == ("discrepancy", tx, False)
    assert send["discrepancy"].endswith(
        "recorded from Exchange BTC, not Kraken BTC; recorded into Wallet, not Cold Storage: it may already be "
        "recorded in Exchange and Wallet")


def test_a_receive_into_another_exchange_is_marked_review(client):
    tx = record(client, "Transfer", WALLET, EXCHANGE_BTC, "0.0006")
    [receive] = into_kraken(client, RECEIVE)
    assert found(receive) == ("discrepancy", tx, False)


def test_a_payout_into_another_exchange_is_marked_review(client):
    tx = record(client, "Deposit", EXTERNAL, EXCHANGE_BTC, "0.00002", source="Interest")
    [payout] = into_kraken(client, PAYOUT)
    assert found(payout) == ("discrepancy", tx, False)
    assert "it may already be recorded in Exchange" in payout["discrepancy"]


# Only the similar pass widens
def test_it_is_never_taken_for_the_rows_copy(client):
    """The exact pass keeps to the row's own account (the owner's rule of
    2026-10-15): two exchanges' identical trades are two trades."""
    record(client, "Buy", BANK, EXCHANGE_BTC, "0.03", cost_basis_usd="1500")
    [buy] = into_kraken(client, BUY)
    assert buy["status"] != "matched"


def test_another_minute_is_still_new(client):
    record(client, "Buy", BANK, EXCHANGE_BTC, "0.03", at="2026-04-07T10:01:00Z", cost_basis_usd="1500")
    [buy] = into_kraken(client, BUY)
    assert found(buy) == ("new", None, False)


def test_another_amount_is_still_new(client):
    record(client, "Buy", BANK, EXCHANGE_BTC, "0.0301", cost_basis_usd="1500")
    record(client, "Transfer", EXCHANGE_BTC, WALLET, "0.0011", fee_amount="0.000005", fee_currency="BTC")
    buy, send = into_kraken(client, BUY, SEND)
    assert found(buy) == ("new", None, False) and found(send) == ("new", None, False)


def test_another_kind_of_transaction_is_still_new(client):
    """A Sell of the same amount and minute in Exchange isn't the file's Buy."""
    record(client, "Sell", EXCHANGE_BTC, EXCHANGE_USD, "0.03", proceeds_usd="1500")
    [buy] = into_kraken(client, BUY)
    assert found(buy) == ("new", None, False)


def test_a_move_between_two_wallets_is_never_the_files_send(client):
    """A transfer from Cold Storage into Wallet at that minute is no
    exchange's send: the wallet side is alike, but the coins left a wallet."""
    record(client, "Transfer", COLD, WALLET, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    [send] = into_kraken(client, SEND, wallet=COLD)
    assert found(send) == ("new", None, False)


def test_a_move_into_the_files_exchange_is_never_its_send(client):
    """Going the same way (the review's finding): coins moved from Exchange
    into Kraken at that minute aren't Kraken's send, nor coins moved from
    Kraken into Exchange its receive."""
    record(client, "Transfer", EXCHANGE_BTC, KRAKEN_BTC, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    record(client, "Transfer", KRAKEN_BTC, EXCHANGE_BTC, "0.0006")
    send, receive = into_kraken(client, SEND, RECEIVE)
    assert found(send) == ("new", None, False) and found(receive) == ("new", None, False)


def test_a_hidden_exchange_is_still_named(client):
    """A hidden account is still yours: the pooled trade recorded there is found."""
    tx = record(client, "Buy", BANK, EXCHANGE_BTC, "0.03", cost_basis_usd="1500")
    assert client.put(f"/api/accounts/{EXCHANGE_BTC}", json={"hidden": True}).status_code == 200
    [buy] = into_kraken(client, BUY)
    assert found(buy) == ("discrepancy", tx, False)
    assert buy["discrepancy"].endswith("it may already be recorded in Exchange")


def test_a_dollar_row_is_never_flagged_this_way(fresh_app, client):
    """Bitcoin amounts only (the owner's words): a dollar deposit into
    Kraken USD beside one into Exchange USD stays new (an exchange's file
    can hold one: dollars in, #581)."""
    record(client, "Deposit", EXTERNAL, EXCHANGE_USD, "500")
    with fresh_app() as db:
        row = RiverProposal(row_number=2, timestamp=datetime(2026, 4, 7, 10, tzinfo=timezone.utc), river_tag=None,
                            type="Deposit", from_account_id=EXTERNAL, to_account_id=KRAKEN_USD,
                            amount=Decimal("500"))
        annotate_duplicates([row], db)
    assert (row.status, row.matched_tx_id) == ("new", None)


def test_the_rows_own_accounts_come_first(client):
    """A transaction in the row's own exchange, only similar (an hour
    earlier), is the one the note names, as before: the other exchange's
    is offered only to a row the other passes leave new."""
    own = record(client, "Buy", BANK, KRAKEN_BTC, "0.03", at="2026-04-07T09:00:00Z", cost_basis_usd="1500")
    record(client, "Buy", BANK, EXCHANGE_BTC, "0.03", cost_basis_usd="1500")
    [buy] = into_kraken(client, BUY)
    assert found(buy) == ("discrepancy", own, False)
    assert "recorded 1 hour earlier" in buy["discrepancy"]


def test_one_transaction_marks_one_row(client):
    """Two identical rows beside one pooled trade: the second is new."""
    tx = record(client, "Buy", BANK, EXCHANGE_BTC, "0.03", cost_basis_usd="1500")
    first, second = into_kraken(client, BUY, BUY)
    assert found(first) == ("discrepancy", tx, False) and found(second) == ("new", None, False)


def test_the_import_saves_it_unless_unticked(client):
    """Similar rows are imported when ticked (never left out by
    themselves), and the second-click guard leaves out only duplicates."""
    record(client, "Buy", BANK, EXCHANGE_BTC, "0.03", cost_basis_usd="1500")
    [buy] = into_kraken(client, BUY)
    row = {k: buy[k] for k in ("row_number", "date", "type", "amount", "from_account", "to_account",
                               "cost_basis_usd")}
    r = client.post("/api/import/river/execute", json={"rows": [row]})
    assert (r.status_code, r.json()["imported_count"], r.json()["skipped_existing"]) == (200, 1, 0), r.text


# The AI's rows name their accounts: their rule is their own
def test_an_ai_buy_into_another_exchange_is_still_ready(client):
    record(client, "Buy", BANK, EXCHANGE_BTC, "0.03", cost_basis_usd="1500")
    r = client.post("/api/import/entries/preview", json={"rows": [{
        "date": AT, "type": "Buy", "amount": "0.03", "from_account": "Bank", "to_account": "Kraken BTC",
        "cost_basis_usd": "1500"}]})
    assert r.status_code == 200, r.text
    [result] = r.json()["results"]
    assert (result["status"], result["matched_transaction_id"]) == ("ready", None)
