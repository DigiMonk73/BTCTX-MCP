"""
The AI key chooses coins (#711, step C5 #733; docs/temp/2.0-coin-choice.md
6.5; the owner's Q4): the AI connector may record coins the user says they
chose by the time the coins left, and see which coins a wallet holds. Its
add (the entry import) takes `chosen_coins` on a row leaving a wallet, its
preview says the coins each such row takes and the coins the wallet holds
then, and its edit takes them too (a list, or null for oldest first). An
edit that changes what leaves without them says what to send, and says so
to the connector (a header), which answers it as the tool's own answer. A
row choosing coins while a lot doesn't know its acquisition replays the
whole ledger (call (j)), so it counts as a replaying one for the AI's copy
and the past-year question; it replays once, before any other row of the
request, so the replay budget always allows it.
"""

from datetime import timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.main import app
from backend.routers import entry_import as entry_router
from backend.schemas.entry_import import EntryRow
from backend.services import entry_import
from backend.services import transaction as tx_service
from backend.services.account import account_book
from backend.tests.test_chosen_coins_711 import (  # noqa: F401  (owner, chose_a2: fixtures)
    LEAVES, chose_a2, coins, deposit, owner, pieces, saved, transfer,
)

SEND_AGAIN = ("Transaction {id} has coins chosen for {btc} BTC leaving Wallet, and this changes what leaves: "
              "choose its coins again (chosen_coins), or set it back to oldest first (chosen_coins: null).")
# A spend the AI is told of: 0.01 BTC and a 0.0001 network fee leave the Wallet
SPENT = {"date": "2025-07-01T12:00:00Z", "type": "Withdrawal", "amount": "0.01", "from_account": "Wallet",
         "to_account": "External", "purpose": "Spent", "proceeds_usd": "1000", "fee_amount": "0.0001",
         "fee_currency": "BTC", "fee_usd": "5"}


@pytest.fixture
def ai(owner) -> TestClient:  # noqa: F811
    assert owner.put("/api/settings/ai-access", json={"on": True}).status_code == 200
    r = owner.post("/api/settings/ai-key")
    assert r.status_code == 200, r.text
    # A 2.0 connector: a ledger of two wallets refuses an older one's writes (#354)
    return TestClient(app, headers={"Authorization": f"Bearer {r.json()['key']}", "X-BitcoinTX-Connector": "2.0.0a2"})


def test_the_ai_adds_a_spend_with_the_coins_the_user_chose(owner, ai):  # noqa: F811
    """The preview lists, for a row leaving a wallet, the coins it takes and
    those the wallet holds before it takes any, oldest first, each with how
    it was acquired, its date acquired, BTC, cost and the term it would have
    on the row's date; the add saves the choice."""
    ids = owner.ids
    row = {**SPENT, "chosen_coins": coins((ids["A2"], "0.0101"))}
    r = ai.post("/api/import/entries/preview", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [result] = r.json()["results"]
    assert result["status"] == "ready", result
    seen = result["simulated"]["coins"]
    assert seen["takes"] == [{"acquired_txn_id": ids["A2"], "row": None, "btc": "0.01010000"}]
    assert seen["held"] == [
        {"acquired_txn_id": ids["A1"], "row": None, "how": "a Deposit (MyBTC) of 2023-01-10 into Wallet",
         "acquired": "2017-03-01", "btc": "0.30000000", "cost_usd": "300.00", "term": "LONG"},
        {"acquired_txn_id": ids["A2"], "row": None, "how": "a Deposit (MyBTC) of 2025-01-15 into Wallet",
         "acquired": "2025-01-15", "btc": "0.50000000", "cost_usd": "45000.00", "term": "SHORT"},
    ]
    assert seen["held_not_listed"] == 0

    r = ai.post("/api/import/entries/execute", json={"rows": [row]})
    assert r.status_code == 200, r.text
    [created] = r.json()["created"]
    stored = owner.get(f"/api/transactions/{created['id']}").json()
    assert stored["chosen_coins"] == [{"acquired_txn_id": ids["A2"], "btc": "0.01010000"}]
    assert stored["coins_chosen_at"]
    assert {piece[0] for piece in pieces(owner, created["id"])} == {ids["A2"]}


def test_the_preview_names_coins_of_its_own_rows_by_their_row(owner, ai):  # noqa: F811
    """A row of the same request has no id yet, so it can't be chosen (the
    AI adds the purchase first), but the wallet holds its coins: they're
    named by their row."""
    deposit = {"date": "2025-06-20T12:00:00Z", "type": "Deposit", "amount": "0.02", "from_account": "External",
               "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "2000"}
    r = ai.post("/api/import/entries/preview", json={"rows": [deposit, SPENT]})
    assert r.status_code == 200, r.text
    _, spent = r.json()["results"]
    held = spent["simulated"]["coins"]["held"]
    assert [(line["acquired_txn_id"], line["row"]) for line in held] == [
        (owner.ids["A1"], None), (owner.ids["A2"], None), (None, 1)]
    # Oldest first takes the 2017 coins: the row chose none
    assert spent["simulated"]["coins"]["takes"] == [{"acquired_txn_id": owner.ids["A1"], "row": None,
                                                    "btc": "0.01010000"}]


def test_the_preview_lists_at_most_200_acquisitions_and_counts_the_rest(owner, ai, monkeypatch):  # noqa: F811
    monkeypatch.setattr(entry_import, "MOST_HELD", 1)
    r = ai.post("/api/import/entries/preview", json={"rows": [SPENT]})
    seen = r.json()["results"][0]["simulated"]["coins"]
    assert [line["acquired_txn_id"] for line in seen["held"]] == [owner.ids["A1"]]
    assert seen["held_not_listed"] == 1
    assert Decimal(seen["held"][0]["btc"]) == Decimal("0.3")


def test_an_exchanges_row_has_no_coins_listed(owner, ai):  # noqa: F811
    """An exchange's coins leave oldest first (#711's call (g)): nothing to choose."""
    owner.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2025-01-20T12:00:00Z", "from_account_id": 99, "to_account_id": 4,
        "amount": "0.1", "fee_amount": "0", "source": "MyBTC", "cost_basis_usd": "9000"})
    sell = {"date": "2025-07-01T12:00:00Z", "type": "Sell", "amount": "0.01", "from_account": "Exchange BTC",
            "to_account": "Exchange USD", "proceeds_usd": "1000", "fee_amount": "0", "fee_currency": "USD"}
    r = ai.post("/api/import/entries/preview", json={"rows": [sell]})
    assert r.json()["results"][0]["simulated"]["coins"] is None


def test_the_ai_edits_a_choice_and_sets_it_back_to_oldest_first(chose_a2, ai):  # noqa: F811
    ids = chose_a2.ids
    r = ai.put(f"/api/transactions/{ids['S']}", json={"chosen_coins": coins((ids["A1"], "0.1001"))})
    assert r.status_code == 200, r.text
    assert r.json()["chosen_coins"] == [{"acquired_txn_id": ids["A1"], "btc": "0.10010000"}]
    r = ai.put(f"/api/transactions/{ids['S']}", json={"chosen_coins": None})
    assert r.status_code == 200, r.text
    assert r.json()["chosen_coins"] is None


def test_an_ai_edit_that_changes_what_leaves_says_to_send_the_coins_again(chose_a2, ai):  # noqa: F811
    """The words a login gets, and a header naming the transaction, so the
    connector answers it as the tool's answer (saved: false), not an error."""
    ids = chose_a2.ids
    r = ai.put(f"/api/transactions/{ids['S']}", json={"amount": "0.2"})
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == SEND_AGAIN.format(id=ids["S"], btc="0.10010000")
    assert r.headers["X-BitcoinTX-Choose-Again"] == str(ids["S"])
    r = ai.put(f"/api/transactions/{ids['S']}", json={"amount": "0.2", "chosen_coins": coins((ids["A2"], "0.2001"))})
    assert r.status_code == 200, r.text
    # Another field keeps the choice
    r = ai.put(f"/api/transactions/{ids['S']}", json={"proceeds_usd": "21000"})
    assert r.status_code == 200, r.text
    assert r.json()["chosen_coins"] == [{"acquired_txn_id": ids["A2"], "btc": "0.20010000"}]


def test_a_logins_edit_gets_the_header_too(chose_a2):  # noqa: F811
    r = chose_a2.put(f"/api/transactions/{chose_a2.ids['S']}", json={"amount": "0.2"})
    assert r.status_code == 422 and r.headers["X-BitcoinTX-Choose-Again"] == str(chose_a2.ids["S"])


def test_the_ai_key_lists_a_saved_transactions_coins_and_nothing_new(owner, ai):  # noqa: F811
    """#706's list for a transaction already saved: a dry run on a scratch
    copy that saves nothing (C5 lists the route on purpose); a new
    transaction's list stays the owner's."""
    moved = saved(owner.post("/api/transactions", json=transfer(LEAVES, "0.05", chosen=coins((owner.ids["A2"], "0.05")))))
    before = owner.get("/api/transactions").json()
    r = ai.post(f"/api/transactions/{moved}/coins-moved", json={})
    assert r.status_code == 200, r.text
    assert [(c["acquired"][:10], c["btc"]) for c in r.json()["coins"]] == [("2025-01-15", "0.05000000")]
    assert owner.get("/api/transactions").json() == before
    assert ai.post("/api/transactions/coins-moved", json=transfer(LEAVES, "0.05")).status_code == 403


# Call (j): a lot that doesn't know its acquisition (made before migration 0101)

def _forget_acquisitions(owner) -> None:  # noqa: F811
    with owner.Session() as db:
        db.execute(text("UPDATE bitcoin_lots SET acquired_txn_id = NULL"))
        db.commit()


def _rows(owner, *rows: dict) -> list[entry_import.PreparedRow]:  # noqa: F811
    with owner.Session() as db:
        prepared = entry_import.validate_rows([EntryRow(**row) for row in rows], timezone.utc, account_book(db))
    assert all(p.result.status == "ready" for p in prepared), [p.result for p in prepared]
    return prepared


@pytest.mark.parametrize("forgotten", [False, True], ids=["lots know", "a lot doesn't"])
def test_a_row_dated_last_choosing_coins_replays_while_a_lot_lacks_its_acquisition(owner, forgotten):  # noqa: F811
    if forgotten:
        _forget_acquisitions(owner)
    chosen = _rows(owner, {**SPENT, "chosen_coins": coins((owner.ids["A2"], "0.0101"))})
    plain = _rows(owner, SPENT)
    with owner.Session() as db:
        assert entry_import.past_year_write(chosen, lambda _db: None).appends(db) is not forgotten
        assert entry_import.past_year_write(plain, lambda _db: None).appends(db) is True
        assert entry_router._recalculates(chosen, db) is forgotten
        assert entry_router._recalculates(plain, db) is False


def test_a_choice_replays_nothing_more_beside_a_backdated_row(owner, ai, monkeypatch):  # noqa: F811
    """A row dated before the ledger's latest sorts before every row dated
    after it and replays the ledger, which gives every lot its acquisition:
    a row choosing coins after it then replays nothing more (call (j)), so
    the AI's budget counts one replay, not two."""
    backdated = {"date": "2024-06-01T12:00:00Z", "type": "Deposit", "amount": "0.01", "from_account": "External",
                 "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "700"}
    rows = [backdated, {**SPENT, "chosen_coins": coins((owner.ids["A2"], "0.0101"))}]
    _forget_acquisitions(owner)
    replay, replays = tx_service.recalculate_all_transactions, []
    monkeypatch.setattr(tx_service, "recalculate_all_transactions",
                        lambda db, **kwargs: (replays.append(1), replay(db, **kwargs))[1])
    with owner.Session() as db:  # the engine's own path, as the add writes its rows
        for p in _rows(owner, *rows):
            tx_service.create_transaction_record(dict(p.tx_data), db, auto_commit=False)
        db.rollback()
    assert replays == [1]
    monkeypatch.setattr(entry_router, "AI_MAX_REPLAYED", 1)  # one replaying row a request
    r = ai.post("/api/import/entries/execute", json={"rows": rows})
    assert r.status_code == 200, r.text


def test_no_coins_are_listed_while_a_lot_lacks_its_acquisition_and_nothing_replays(owner, ai):  # noqa: F811
    """Lots made before migration 0101 don't know their acquisition: listed,
    they'd be one line, dated as the first (the 2025 coins long-term). A
    preview that replays nothing says so instead, and its figures are the
    save's (no replay of its own: a recalculation could move them)."""
    _forget_acquisitions(owner)
    [result] = ai.post("/api/import/entries/preview", json={"rows": [SPENT]}).json()["results"]
    assert result["simulated"]["coins"] is None
    assert entry_import.COINS_NOT_LISTED in result["warnings"]


def test_a_choice_that_replays_lists_the_rows_before_it_too(owner, ai):  # noqa: F811
    """Call (j): the row choosing coins replays the ledger, which hands every
    row of the request over again, with each lot's own acquisition."""
    _forget_acquisitions(owner)
    rows = [SPENT, {**SPENT, "date": "2025-07-02T12:00:00Z", "chosen_coins": coins((owner.ids["A2"], "0.0101"))}]
    first, second = ai.post("/api/import/entries/preview", json={"rows": rows}).json()["results"]
    for result in (first, second):
        held = result["simulated"]["coins"]["held"]
        assert [(line["acquired_txn_id"], line["term"]) for line in held] == [
            (owner.ids["A1"], "LONG"), (owner.ids["A2"], "SHORT")], result
    assert entry_import.COINS_NOT_LISTED not in first["warnings"]


def test_a_transfer_takes_inherited_coins_it_chose_its_fee_from_the_oldest_chosen(owner, ai):  # noqa: F811
    """The fee is paid by the chosen coins, the oldest of them first (#711's
    call (b)); a Transfer's takes are its fee's and the coins it moves;
    inherited coins are INHERITED and long-term whenever they leave."""
    ids = owner.ids
    ids["I"] = deposit(owner, "2025-02-01T12:00:00Z", "0.2", "20000", acquired="2024-12-20", source="Inherited")
    move = {"date": "2025-07-01T12:00:00Z", "type": "Transfer", "amount": "0.0501", "from_account": "Wallet",
            "to_account": "Cold Storage", "fee_amount": "0.0001", "fee_currency": "BTC", "fee_usd": "5",
            "chosen_coins": coins((ids["I"], "0.03"), (ids["A2"], "0.0201"))}
    r = ai.post("/api/import/entries/preview", json={"rows": [move]})
    assert r.status_code == 200, r.text
    seen = r.json()["results"][0]["simulated"]["coins"]
    # The inherited coins, of a death on 2024-12-20, are the oldest chosen: the fee and 0.0299 of the move
    assert seen["takes"] == [{"acquired_txn_id": ids["I"], "row": None, "btc": "0.03000000"},
                             {"acquired_txn_id": ids["A2"], "row": None, "btc": "0.02010000"}]
    assert [(line["acquired_txn_id"], line["acquired"], line["term"]) for line in seen["held"]] == [
        (ids["A1"], "2017-03-01", "LONG"), (ids["I"], "INHERITED", "LONG"), (ids["A2"], "2025-01-15", "SHORT")]


def test_the_ai_copy_comes_first_for_a_row_that_replays_by_its_choice(owner, ai, monkeypatch):  # noqa: F811
    copies = []
    monkeypatch.setattr(entry_router, "_copy_before_ai_changes", lambda db, refused: copies.append(refused))
    row = {**SPENT, "chosen_coins": coins((owner.ids["A2"], "0.0101"))}
    _forget_acquisitions(owner)
    r = ai.post("/api/import/entries/execute", json={"rows": [row]})
    assert r.status_code == 200, r.text
    assert copies and set(copies) == {"Not added"}
