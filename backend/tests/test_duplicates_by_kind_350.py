"""
The duplicate check with multiple wallets, exchanges or banks (card B5a
#350). The owner's rule (2026-10-15), refining #253's for multiple
accounts: a recorded transaction isn't a row's copy when, on the same side,
the two name different accounts of the same kind and currency (two wallets,
two exchanges' BTC or USD accounts, two banks); External, or accounts of
different kinds, still match as before. It holds for River's rows and the
AI's (5.11). River's guessed wallet (the owner's decision, 2026-10-16): a
send's or receive's wallet is the file's choice, not River's word, so a
copy that differs only there is never paired and never in the rough pass,
but offered to the similar pass: marked Review, ticked, its note naming the
other wallet's transaction. A 1.x ledger has no two accounts of one kind
and currency, so its matches stay as they were.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.account_pairs import add_them
from backend.tests.conftest import default_login, stub_daily_prices, stub_prices_at

HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"
WHEN, AT = "2026-02-15 10:00:00", "2026-02-15T10:00:00Z"
SEND = f"{WHEN},0.00100000,BTC,,,0.00000500,BTC,"  # its Transfer's amount: 0.001005 with its fee
RECEIVE = f"{WHEN},,,0.00060000,BTC,,,"
WALLET, EXCHANGE_BTC, COLD, KRAKEN_BTC = 2, 4, 100, 103


@pytest.fixture
def client(fresh_app, monkeypatch) -> TestClient:
    """A ledger with a second wallet and a second exchange (account_pairs'
    ids), to record transactions into."""
    stub_daily_prices(monkeypatch, lambda day: 100000.0)
    stub_prices_at(monkeypatch, lambda when: 100000)
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    add_them(client)
    record(client, "Deposit", 99, EXCHANGE_BTC, "1", at="2026-01-01T12:00:00Z", source="MyBTC", cost_basis_usd="1")
    record(client, "Deposit", 99, KRAKEN_BTC, "1", at="2026-01-01T12:00:00Z", source="MyBTC", cost_basis_usd="1")
    record(client, "Deposit", 99, COLD, "1", at="2026-01-01T12:00:00Z", source="MyBTC", cost_basis_usd="1")
    return client


def record(client: TestClient, tx_type: str, from_id: int, to_id: int, amount: str, at: str = AT, **more) -> int:
    r = client.post("/api/transactions", json={"type": tx_type, "timestamp": at, "from_account_id": from_id,
                                               "to_account_id": to_id, "amount": amount, **more})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def river(client: TestClient, *rows: str) -> list[dict]:
    content = ("\n".join([HEADER, *rows]) + "\n").encode()
    r = client.post("/api/import/river/preview", files={"file": ("river.csv", content, "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()["proposals"]


def found(proposal: dict) -> tuple:
    return proposal["status"], proposal["matched_tx_id"], proposal["near_amount"]


# River: the exchange side is the owner's choice for the file
def test_another_exchanges_send_to_the_wallet_is_never_this_ones(client):
    """Exchange B's send left out as exchange A's: B's coins would never
    leave B (the bug the rule closes)."""
    record(client, "Transfer", KRAKEN_BTC, WALLET, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    [send] = river(client, SEND)
    assert found(send) == ("new", None, False) and send["discrepancy"] is None


def test_a_deposit_typed_into_the_wallet_still_matches_the_send(client):
    """External on one side, the same wallet on the other: as in 1.x, the
    deposit the owner typed for those coins is the send (#253)."""
    tx = record(client, "Deposit", 99, WALLET, "0.001", source="MyBTC", cost_basis_usd="100")
    [send] = river(client, SEND)
    assert found(send) == ("matched", tx, False)


def test_the_same_send_is_still_matched(client):
    tx = record(client, "Transfer", EXCHANGE_BTC, WALLET, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    [send] = river(client, SEND)
    assert found(send) == ("matched", tx, False)


# River: the wallet side is the file's guess
def test_a_send_typed_into_the_other_wallet_is_marked_review(client):
    tx = record(client, "Transfer", EXCHANGE_BTC, COLD, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    [send] = river(client, SEND)
    assert found(send) == ("discrepancy", tx, False)  # ticked: imported unless the owner unticks it
    assert send["discrepancy"] == (f"Same BTC amount as tx #{tx} (Transfer 0.00100500 BTC), the same minute; "
                                   "recorded into Cold Storage, not Wallet: it may be the same transaction")


def test_a_receive_typed_from_the_other_wallet_is_marked_review(client):
    tx = record(client, "Transfer", COLD, EXCHANGE_BTC, "0.0006")
    [receive] = river(client, RECEIVE)
    assert found(receive) == ("discrepancy", tx, False)
    assert "recorded from Cold Storage, not Wallet" in receive["discrepancy"]


def test_a_deposit_typed_into_the_other_wallet_is_marked_review(client):
    """The deposit the owner typed for those coins, into the wallet the file
    didn't guess: linked to the send only by that wallet (the review's
    finding: no candidate at all before)."""
    tx = record(client, "Deposit", 99, COLD, "0.001", source="MyBTC", cost_basis_usd="100")
    [send] = river(client, SEND)
    assert found(send) == ("discrepancy", tx, False)
    assert "recorded into Cold Storage, not Wallet" in send["discrepancy"]


def test_a_withdrawal_typed_from_the_other_wallet_is_marked_review(client):
    tx = record(client, "Withdrawal", COLD, 99, "0.0006", purpose="Spent", proceeds_usd="60")
    [receive] = river(client, RECEIVE)
    assert found(receive) == ("discrepancy", tx, False)
    assert "recorded from Cold Storage, not Wallet" in receive["discrepancy"]


def test_the_other_wallets_send_of_a_near_amount_isnt_offered(client):
    """Never in the rough pass, whose Review rows start unticked."""
    record(client, "Transfer", EXCHANGE_BTC, COLD, "0.0011", fee_amount="0.000005", fee_currency="BTC")
    [send] = river(client, SEND)
    assert found(send) == ("new", None, False)


def test_the_same_send_from_another_exchange_into_the_other_wallet_isnt_marked(client):
    record(client, "Transfer", KRAKEN_BTC, COLD, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    [send] = river(client, SEND)
    assert found(send) == ("new", None, False)


def test_the_wallet_chosen_for_the_file_is_the_one_compared(client):
    tx = record(client, "Transfer", EXCHANGE_BTC, COLD, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    content = ("\n".join([HEADER, SEND]) + "\n").encode()
    r = client.post("/api/import/river/preview", files={"file": ("river.csv", content, "text/csv")},
                    data={"wallet_account_id": str(COLD)})
    [send] = r.json()["proposals"]
    assert send["to_account"] == "Cold Storage"
    assert found(send) == ("matched", tx, False)


# The AI's rows: the accounts are the AI's, nothing guessed
def ai_preview(client: TestClient, **row) -> dict:
    payload = {"date": AT, "type": "Deposit", "amount": "0.01", "from_account": "External",
               "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "500", **row}
    r = client.post("/api/import/entries/preview", json={"rows": [payload]})
    assert r.status_code == 200, r.text
    [result] = r.json()["results"]
    return result


def test_an_ai_row_into_one_wallet_isnt_another_wallets_deposit(client):
    record(client, "Deposit", 99, COLD, "0.01", source="MyBTC", cost_basis_usd="500")
    result = ai_preview(client)
    assert (result["status"], result["matched_transaction_id"]) == ("ready", None)


def test_an_ai_row_beside_another_exchanges_send_isnt_its_copy(client):
    record(client, "Transfer", KRAKEN_BTC, WALLET, "0.01", fee_amount="0.0001", fee_currency="BTC")
    result = ai_preview(client, type="Transfer", from_account="Exchange BTC", source=None, cost_basis_usd=None,
                        fee_amount="0.0001", fee_currency="BTC")
    assert (result["status"], result["matched_transaction_id"]) == ("ready", None)


def test_an_ai_row_into_another_kind_of_account_is_still_only_similar(client):
    """#522's rule stands: a payout into Exchange BTC beside one recorded
    into Wallet is only similar, its note naming the account."""
    tx = record(client, "Deposit", 99, EXCHANGE_BTC, "0.01", source="MyBTC", cost_basis_usd="500")
    result = ai_preview(client)
    assert (result["status"], result["matched_transaction_id"]) == ("possible_duplicate", tx)
    assert "recorded into Exchange BTC, not Wallet" in " ".join(result["warnings"])


def test_a_1x_ledgers_notes_are_as_they_were(fresh_app, monkeypatch):
    """One wallet: the guessed side never names another one, so a note says
    nothing of it (the review's finding: it said "recorded into External,
    not Wallet" beside a withdrawal)."""
    stub_daily_prices(monkeypatch, lambda day: 100000.0)
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    record(client, "Deposit", 99, EXCHANGE_BTC, "1", at="2026-01-01T12:00:00Z", source="MyBTC", cost_basis_usd="1")
    tx = record(client, "Withdrawal", EXCHANGE_BTC, 99, "0.001", at="2026-02-15T07:00:00Z", purpose="Spent",
                proceeds_usd="100")
    [send] = river(client, SEND)
    assert (found(send), send["discrepancy"]) == (("discrepancy", tx, False), (
        f"Same BTC amount as tx #{tx} (Withdrawal 0.00100000 BTC), recorded 3 hours earlier: it may be the same "
        "transaction"))


# River's funding bank: never River's word (the build lead's call, 2026-10-23,
# under the owner's decision 25): a second bank still matches exactly
RECURRING = [f"2026-03-0{day} 12:00:00,25.00,USD,0.000{day}0000,BTC,,,Buy" for day in range(2, 6)]
CREDIT_UNION = 101


def test_buys_paid_from_the_second_bank_are_found_again(client):
    """Four recurring buys imported with their funding set to the second
    bank, then the same file again (its default: the first bank): each is
    already recorded, never imported twice."""
    first = river(client, *RECURRING)
    assert {p["from_account"] for p in first} == {"Bank"}
    rows = [{k: p[k] for k in ("row_number", "date", "type", "amount", "to_account", "cost_basis_usd")}
            | {"from_account": "Credit Union"} for p in first]
    r = client.post("/api/import/river/execute", json={"rows": rows})
    assert r.status_code == 200 and r.json()["imported_count"] == 4, r.text
    saved = {t["id"] for t in client.get("/api/transactions").json() if t["from_account_id"] == CREDIT_UNION}
    again = river(client, *RECURRING)
    assert {p["status"] for p in again} == {"matched"}
    assert {p["matched_tx_id"] for p in again} == saved


def test_the_ais_buy_names_its_bank(client):
    """The AI's rows name their accounts: a buy paid from another bank is
    another buy (the owner's rule of 2026-10-15 stands for them)."""
    record(client, "Buy", CREDIT_UNION, EXCHANGE_BTC, "0.01", cost_basis_usd="500")
    result = ai_preview(client, type="Buy", from_account="Bank", to_account="Exchange BTC", source=None,
                        cost_basis_usd="500")
    assert (result["status"], result["matched_transaction_id"]) == ("ready", None)


def test_a_resend_with_another_funding_bank_is_skipped(client):
    """The execute's double-submit guard: the same buys sent again (a second
    tab, a resend after editing the funding) are already recorded, whichever
    bank each names (the re-check's finding: no test held the guard's flag)."""
    rows = [{k: p[k] for k in ("row_number", "date", "type", "amount", "from_account", "to_account",
                               "cost_basis_usd")} for p in river(client, *RECURRING)]
    first = client.post("/api/import/river/execute", json={"rows": rows})
    assert first.status_code == 200 and first.json()["imported_count"] == 4, first.text
    again = client.post("/api/import/river/execute",
                        json={"rows": [dict(row, from_account="Credit Union") for row in rows]})
    assert (again.json()["imported_count"], again.json()["skipped_existing"]) == (0, 4), again.text


def test_a_move_between_two_wallets_is_never_rivers_send(client):
    """The guessed side counts as the same way only beside the row's own
    exchange or External: a transfer from Wallet to Cold Storage isn't the
    exchange's send to Wallet, nor one from Cold Storage to Wallet its
    receive (the re-check's finding)."""
    record(client, "Deposit", 99, WALLET, "1", at="2026-01-01T12:00:00Z", source="MyBTC", cost_basis_usd="1")
    record(client, "Transfer", WALLET, COLD, "0.001005", fee_amount="0.000005", fee_currency="BTC")
    record(client, "Transfer", COLD, WALLET, "0.0006")
    send, receive = river(client, SEND, RECEIVE)
    assert found(send) == ("new", None, False) and found(receive) == ("new", None, False)
