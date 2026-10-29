"""
The 2.0 connector on a BitcoinTX 1.x (#834): 1.x has no choice of coins, so
it ignored chosen_coins and saved the spend first in, first out, while the
connector answered success; get_coins_moved answered "405: Method Not
Allowed". Against a BitcoinTX before 2.0 (its AI key can't read the account
list: 403, or 404) the connector now refuses a choice of coins, in a preview,
an add or an edit, and get_coins_moved, before sending anything, in plain
words. [] (oldest first, what 1.x does) still goes, and so does everything
else 1.x can do; a BitcoinTX updated to 2.0 during the run takes the choice.
The server here is 2.0's with the account list answered as 1.x answers it,
so the old code's request would have been saved.
"""

from contextlib import asynccontextmanager

import pytest
from mcp import Client

from btctx_mcp import server
from test_account_names_350 import Recording, connect
from test_server import backend_db, call  # noqa: F401  (fixture)

pytestmark = [pytest.mark.anyio, pytest.mark.parametrize("status", [403, 404])]

DEPOSIT = {"date": "2025-01-15T12:00:00Z", "type": "Deposit", "amount": "0.5", "from_account": "External",
           "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "45000"}
SPENT = {"date": "2025-07-01T12:00:00Z", "type": "Withdrawal", "amount": "0.01", "from_account": "Wallet",
         "to_account": "External", "purpose": "Spent", "proceeds_usd": "1000", "fee_amount": "0.0001",
         "fee_currency": "BTC", "fee_usd": "5"}
LATER = {**SPENT, "date": "2025-08-01T12:00:00Z"}
CHOICE = ("This BitcoinTX is 1.x: choosing which coins move needs BitcoinTX 2.0. Nothing was saved. Without the "
          "choice, 1.x sends the oldest coins first, not the ones the user chose: tell them, and leave chosen_coins "
          "out only if they say so.")
LISTING = "This BitcoinTX is 1.x: listing the coins a transaction moves needs BitcoinTX 2.0."


@pytest.fixture
def anyio_backend():
    return "asyncio"


@asynccontextmanager
async def on_1x(engine, status: int):
    """A connector run against a BitcoinTX that answers the account list as
    1.x does (403 or 404), holding a deposit into Wallet and a spend from it:
    (client, transport, the deposit's id, the spend's id)."""
    transport = Recording(answers={"/api/accounts/": (status, "Not Found")})
    btctx = await connect(engine, transport)
    try:
        async with Client(server.mcp) as client:
            deposit = (await call(client, "add_transactions", {"transactions": [DEPOSIT]}))["created"][0]["id"]
            spent = (await call(client, "add_transactions", {"transactions": [SPENT]}))["created"][0]["id"]
            transport.seen.clear()
            yield client, transport, deposit, spent
    finally:
        server.set_client(None)
        await btctx.aclose()


def writes(transport: Recording) -> list[tuple[str, str]]:
    """What the run asked BitcoinTX to do besides reading."""
    return [(method, path) for method, path, _ in transport.seen if method != "GET"]


@pytest.mark.parametrize("tool", ["preview_transactions", "add_transactions"])
async def test_a_row_choosing_coins_is_refused_before_it_is_sent(backend_db, status, tool):  # noqa: F811
    async with on_1x(backend_db, status) as (client, transport, deposit, _):
        # Only the second row chooses: one such row refuses the request
        rows = [{**LATER, "date": "2025-07-15T12:00:00Z"},
                {**LATER, "chosen_coins": [{"acquired_txn_id": deposit, "btc": "0.0101"}]}]
        text = await call(client, tool, {"transactions": rows}, expect_error=True)
        assert text.endswith(CHOICE), text
        assert writes(transport) == []
        assert (await call(client, "list_transactions"))["total_matching"] == 2


# The choice alone, or with other changes (each a valid choice on 2.0, which the old code saved)
@pytest.mark.parametrize("more, btc", [
    ({}, "0.0101"),
    ({"date": "2025-07-02T12:00:00Z", "amount": "0.02", "proceeds_usd": "2000"}, "0.0201"),
])
async def test_an_edit_choosing_coins_is_refused_before_it_is_sent(backend_db, status, more, btc):  # noqa: F811
    async with on_1x(backend_db, status) as (client, transport, deposit, spent):
        text = await call(client, "update_transaction", {
            "transaction_id": spent, **more, "chosen_coins": [{"acquired_txn_id": deposit, "btc": btc}]},
            expect_error=True)
        assert text.endswith(CHOICE), text
        assert writes(transport) == []


async def test_get_coins_moved_is_refused_in_plain_words(backend_db, status):  # noqa: F811
    async with on_1x(backend_db, status) as (client, transport, _, spent):
        text = await call(client, "get_coins_moved", {"transaction_id": spent}, expect_error=True)
        assert text.endswith(LISTING), text
        assert writes(transport) == []


async def test_oldest_first_and_rows_1x_knows_still_go(backend_db, status):  # noqa: F811
    async with on_1x(backend_db, status) as (client, transport, _, spent):
        updated = await call(client, "update_transaction", {"transaction_id": spent, "chosen_coins": []})
        assert updated["id"] == spent and "chosen_coins" not in updated
        assert ("PUT", f"/api/transactions/{spent}") in writes(transport)
        added = await call(client, "add_transactions", {"transactions": [{**LATER, "chosen_coins": []}]})
        assert added["imported_count"] == 1


async def test_a_bitcointx_updated_to_2_0_during_the_run_takes_the_choice(backend_db, status):  # noqa: F811
    async with on_1x(backend_db, status) as (client, transport, deposit, _):
        del transport.answers["/api/accounts/"]  # it lists its accounts now: 2.0
        row = {**LATER, "chosen_coins": [{"acquired_txn_id": deposit, "btc": "0.0101"}]}
        added = await call(client, "add_transactions", {"transactions": [row]})
        assert added["imported_count"] == 1
        [listed] = [t for t in (await call(client, "list_transactions"))["transactions"]
                    if t["id"] == added["created"][0]["id"]]
        assert listed["chosen_coins"] == [{"acquired_txn_id": deposit, "btc": "0.01010000"}]
