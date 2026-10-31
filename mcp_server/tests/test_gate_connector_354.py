"""
The connector and the gate (2.0 spec 5.10, 5.12; card B7a #354): a 2.0
connector saves into the user's added wallets and exchanges by their names,
and its every request says it is one (X-BitcoinTX-Connector). A connector
without that header, as every 1.x one is, can still read a ledger with a
second wallet or exchange, but BitcoinTX refuses its writes there: the
tool's answer passes the 409's words on, so the AI tells the user to update.
"""

import httpx
import pytest
from mcp import Client
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.services import account as account_service
from backend.services.ai_key import OLD_CONNECTOR
from btctx_mcp import server
from btctx_mcp.client import CONNECTOR_HEADER, BtctxClient
from test_server import backend_db, call, make_ai_key  # noqa: F401  (fixture)

pytestmark = pytest.mark.anyio

ROWS = [
    {"date": "2026-01-10T12:00:00Z", "type": "Deposit", "amount": "0.2", "from_account": "External",
     "to_account": "Coldcard", "source": "MyBTC", "cost_basis_usd": "18000.00"},
    {"date": "2026-01-11T12:00:00Z", "type": "Transfer", "amount": "0.1", "from_account": "Coldcard",
     "to_account": "Kraken BTC", "fee_amount": "0", "fee_currency": "BTC"},
    {"date": "2026-01-12T12:00:00Z", "type": "Sell", "amount": "0.1", "from_account": "kraken btc",
     "to_account": "Kraken USD", "proceeds_usd": "10000.00", "fee_amount": "10", "fee_currency": "USD"},
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def connector(backend_db):  # noqa: F811
    """A ledger with a second wallet and a second exchange; yields a
    function giving an MCP client, a 2.0 connector's or one without its header."""
    with sessionmaker(bind=backend_db)() as db:
        account_service.add_account(db, "wallet", "Coldcard")
        account_service.add_account(db, "exchange", "Kraken")
    key = make_ai_key(backend_db)
    made = []

    def open_one(old: bool = False) -> Client:
        btctx = BtctxClient(base_url="http://testserver", ai_key=key, transport=httpx.ASGITransport(app=app))
        if old:
            del btctx._http.headers[CONNECTOR_HEADER]  # as a 1.x connector asks
        made.append(btctx)
        server.set_client(btctx)
        return Client(server.mcp)

    yield open_one
    server.set_client(None)
    for btctx in made:
        await btctx.aclose()


async def test_a_2_0_connector_saves_into_the_added_wallet_and_exchange(connector):
    async with connector() as mcp:
        added = await call(mcp, "add_transactions", {"transactions": ROWS})
        assert added["imported_count"] == 3, added
        listed = await call(mcp, "list_transactions", {"account": "Kraken BTC"})
    assert sorted((t["type"], t["from"], t["to"]) for t in listed["transactions"]) == [
        ("Sell", "Kraken BTC", "Kraken USD"), ("Transfer", "Coldcard", "Kraken BTC")]


async def test_a_connector_without_its_header_reads_but_cant_write(connector):
    async with connector() as mcp:
        await call(mcp, "add_transactions", {"transactions": ROWS[:1]})
    async with connector(old=True) as mcp:
        listed = await call(mcp, "list_transactions", {})
        assert listed["total_matching"] == 1
        refused = await call(mcp, "add_transactions", {"transactions": ROWS[1:2]}, expect_error=True)
        assert OLD_CONNECTOR in refused
        assert (await call(mcp, "list_transactions", {}))["total_matching"] == 1
