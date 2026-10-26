"""
The connector chooses coins (#711, step C5 #733; the owner's Q4): a row
leaving one of the user's wallets may name the coins the user says they
chose by the time they left (chosen_coins: each Buy or Deposit by its
transaction id, and the BTC from it), the preview says which coins each
such row takes and which the wallet holds then, list_transactions shows a
choice and when it was saved, update_transaction changes it ([] for oldest
first), and get_coins_moved shows the coins a saved transaction moves. An
edit that changes what leaves a row with a choice, without the coins, is
the tool's answer (saved: false, what to send), never an error.
"""

import pytest
from sqlalchemy.orm import sessionmaker

from backend.services import account as account_service
from test_server import backend_db, call, mcp_client  # noqa: F401  (fixtures)

pytestmark = pytest.mark.anyio

OLD = {"date": "2023-01-10T12:00:00Z", "type": "Deposit", "amount": "0.3", "from_account": "External",
       "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "300", "acquired_at": "2017-03-01"}
NEW = {**OLD, "date": "2025-01-15T12:00:00Z", "amount": "0.5", "cost_basis_usd": "45000", "acquired_at": None}
SPENT = {"date": "2025-07-01T12:00:00Z", "type": "Withdrawal", "amount": "0.01", "from_account": "Wallet",
         "to_account": "External", "purpose": "Spent", "proceeds_usd": "1000", "fee_amount": "0.0001",
         "fee_currency": "BTC", "fee_usd": "5"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _acquired(mcp_client) -> tuple[int, int]:  # noqa: F811
    added = await call(mcp_client, "add_transactions", {"transactions": [OLD, {k: v for k, v in NEW.items() if v}]})
    return tuple(c["id"] for c in added["created"])


async def test_a_spend_of_the_coins_the_user_chose_is_previewed_added_and_listed(mcp_client):  # noqa: F811
    old, new = await _acquired(mcp_client)
    spent = {**SPENT, "chosen_coins": [{"acquired_txn_id": new, "btc": "0.0101"}]}
    preview = await call(mcp_client, "preview_transactions", {"transactions": [spent]})
    seen = preview["results"][0]["simulated"]["coins"]
    assert [(line["acquired_txn_id"], line["btc"]) for line in seen["takes"]] == [(new, "0.01010000")]
    assert [(line["acquired_txn_id"], line["acquired"], line["term"]) for line in seen["held"]] == [
        (old, "2017-03-01", "LONG"), (new, "2025-01-15", "SHORT")]

    added = await call(mcp_client, "add_transactions", {"transactions": [spent]})
    spent_id = added["created"][0]["id"]
    assert added["created"][0]["holding_period"] == "SHORT"  # the 2025 coins, not the 2017 ones
    [listed] = (await call(mcp_client, "list_transactions", {"type": "Withdrawal"}))["transactions"]
    assert listed["id"] == spent_id
    assert listed["chosen_coins"] == [{"acquired_txn_id": new, "btc": "0.01010000"}]
    assert listed["coins_chosen_at"]


async def test_an_edit_changes_the_coins_and_sets_them_back_to_oldest_first(mcp_client):  # noqa: F811
    old, new = await _acquired(mcp_client)
    spent = {**SPENT, "chosen_coins": [{"acquired_txn_id": new, "btc": "0.0101"}]}
    spent_id = (await call(mcp_client, "add_transactions", {"transactions": [spent]}))["created"][0]["id"]

    updated = await call(mcp_client, "update_transaction", {
        "transaction_id": spent_id, "chosen_coins": [{"acquired_txn_id": old, "btc": "0.0101"}]})
    assert updated["chosen_coins"] == [{"acquired_txn_id": old, "btc": "0.01010000"}]
    assert updated["holding_period"] == "LONG"

    updated = await call(mcp_client, "update_transaction", {"transaction_id": spent_id, "chosen_coins": []})
    assert "chosen_coins" not in updated and "coins_chosen_at" not in updated


async def test_an_edit_that_changes_what_leaves_says_to_choose_the_coins_again(mcp_client):  # noqa: F811
    _, new = await _acquired(mcp_client)
    spent = {**SPENT, "chosen_coins": [{"acquired_txn_id": new, "btc": "0.0101"}]}
    spent_id = (await call(mcp_client, "add_transactions", {"transactions": [spent]}))["created"][0]["id"]

    answer = await call(mcp_client, "update_transaction", {"transaction_id": spent_id, "amount": "0.02"})
    assert answer["saved"] is False
    assert answer["detail"].startswith(f"Transaction {spent_id} has coins chosen for 0.01010000 BTC leaving Wallet")
    assert "chosen_coins" in answer["to_go_on"]

    updated = await call(mcp_client, "update_transaction", {
        "transaction_id": spent_id, "amount": "0.02", "chosen_coins": [{"acquired_txn_id": new, "btc": "0.0201"}]})
    assert updated["amount"].startswith("0.02") and updated["chosen_coins"][0]["btc"] == "0.02010000"


async def test_get_coins_moved_shows_what_a_saved_transfer_moves(mcp_client, backend_db):  # noqa: F811
    with sessionmaker(bind=backend_db)() as db:
        account_service.add_account(db, "wallet", "Cold Storage")
    _, new = await _acquired(mcp_client)
    move = {"date": "2025-06-01T12:00:00Z", "type": "Transfer", "amount": "0.05", "from_account": "Wallet",
            "to_account": "Cold Storage", "fee_amount": "0", "fee_currency": "BTC",
            "chosen_coins": [{"acquired_txn_id": new, "btc": "0.05"}]}
    move_id = (await call(mcp_client, "add_transactions", {"transactions": [move]}))["created"][0]["id"]
    moved = await call(mcp_client, "get_coins_moved", {"transaction_id": move_id})
    assert [(c["acquired"][:10], c["btc"]) for c in moved["coins"]] == [("2025-01-15", "0.05000000")]


async def test_the_guide_says_when_coins_may_be_chosen(mcp_client):  # noqa: F811
    guide = await call(mcp_client, "get_ledger_guide")
    flat = " ".join(guide.split()) if isinstance(guide, str) else ""
    assert "can't record coins the user identified" not in flat
    for words in ("chosen_coins", "by the time they left", "never suggest", "oldest first"):
        assert words in flat, words
