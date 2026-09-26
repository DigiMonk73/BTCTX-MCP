"""
End-to-end tests: MCP client -> btctx_mcp server -> BitcoinTX FastAPI app
(in-process via ASGI transport) -> temporary SQLite database.

Run from the repo root:
    PYTHONPATH=$(pwd):$(pwd)/mcp_server pytest mcp_server/tests
"""

import json
import os
import re
import tempfile
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from mcp import Client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from backend.tests.conftest import LOGIN_CREDS, init_test_db
from btctx_mcp import server
from btctx_mcp.client import BtctxClient

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def backend_db(monkeypatch):
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    engine = create_engine(f"sqlite:///{tmp.name}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    Session = sessionmaker(bind=engine)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    async def fake_historical(date: str):
        return {"USD": 50000.0}

    async def fake_current():
        return {"USD": 60000.0}

    async def no_bulk_history(start, end):
        return {}

    monkeypatch.setattr("backend.services.price_history.fetch_range", no_bulk_history)
    monkeypatch.setattr("backend.services.bitcoin.get_historical_price", fake_historical)
    monkeypatch.setattr("backend.services.bitcoin.get_current_price", fake_current)
    monkeypatch.setattr(
        "backend.services.transaction.get_btc_price", lambda timestamp, db: Decimal("50000")
    )
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(tmp.name)


@pytest.fixture
async def mcp_client(backend_db):
    btctx = BtctxClient(
        base_url="http://testserver",
        username=LOGIN_CREDS["username"],
        password=LOGIN_CREDS["password"],
        transport=httpx.ASGITransport(app=app),
    )
    server.set_client(btctx)
    async with Client(server.mcp) as client:
        yield client
    server.set_client(None)
    await btctx.aclose()


async def call(client, name, args=None, expect_error=False):
    result = await client.call_tool(name, args or {})
    text = "".join(getattr(c, "text", "") for c in result.content)
    assert bool(result.is_error) == expect_error, text
    if expect_error:
        return text
    return json.loads(text)  # the text block is what the model reads


# A River buy, then the whole balance to cold storage (amount includes the fee)
BUY = {
    "date": "2024-01-15T14:00:00Z", "type": "Buy", "amount": "0.01",
    "from_account": "Bank", "to_account": "Exchange BTC",
    "cost_basis_usd": "420.00", "fee_amount": "4.20", "fee_currency": "USD",
}
TO_COLD = {
    "date": "2024-01-16T09:00:00Z", "type": "Transfer", "amount": "0.01",
    "from_account": "Exchange BTC", "to_account": "Wallet",
    "fee_amount": "0.0001", "fee_currency": "BTC",
}


async def test_tools_listed_without_bulk_delete(mcp_client):
    tools = {t.name for t in (await mcp_client.list_tools()).tools}
    assert tools == {
        "get_ledger_guide", "get_portfolio", "list_transactions", "get_btc_price",
        "preview_transactions", "add_transactions", "update_transaction", "delete_transaction",
        "recalculate_ledger", "review_ledger",
    }


async def test_ai_setup_guide_names_real_tools(mcp_client):
    """AI_SETUP.md tells the AI which tools to call; they must exist."""
    tools = {t.name for t in (await mcp_client.list_tools()).tools}
    guide = (Path(__file__).parents[1] / "AI_SETUP.md").read_text()
    named = set(re.findall(r"`([a-z]+_[a-z_]+)`", guide))
    assert {"get_portfolio", "get_ledger_guide"} <= named
    assert named <= tools


async def test_ai_setup_guide_names_the_startos_certificate_file():
    """The guide tells the AI what to save StartOS's root CA as; it must be the
    file name the StartOS Connect an AI Assistant action tells the user."""
    repo = Path(__file__).parents[2]
    action = (repo / "startos/startos/actions/connectAi.ts").read_text()
    [ca_file] = re.findall(r"const CA_FILE = '([^']+)'", action)
    assert f"`{ca_file}`" in (repo / "mcp_server/AI_SETUP.md").read_text()


async def test_preview_then_add_then_list(mcp_client):
    preview = await call(mcp_client, "preview_transactions", {"transactions": [BUY, TO_COLD]})
    assert preview["ok"] is True
    assert preview["ready_count"] == 2
    assert (await call(mcp_client, "list_transactions"))["total_matching"] == 0

    added = await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD]})
    assert added["imported_count"] == 2

    listed = await call(mcp_client, "list_transactions", {"account": "Wallet"})
    assert listed["total_matching"] == 1
    tx = listed["transactions"][0]
    assert (tx["type"], tx["from"], tx["to"]) == ("Transfer", "Exchange BTC", "Wallet")

    again = await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD]})
    assert again["imported_count"] == 0 and again["skipped_duplicates"] == 2


async def test_income_deposit_autofills_basis(mcp_client):
    dep = {
        "date": "2024-02-01", "type": "Deposit", "amount": "0.002",
        "from_account": "External", "to_account": "Wallet", "source": "Income",
    }
    res = (await call(mcp_client, "preview_transactions", {"transactions": [dep]}))["results"][0]
    assert res["autofilled_fields"] == ["cost_basis_usd"]
    assert Decimal(res["normalized"]["cost_basis_usd"]) == Decimal("100.00")


async def test_schema_rejects_unknown_account(mcp_client):
    bad = dict(BUY, to_account="Coldcard")
    await call(mcp_client, "preview_transactions", {"transactions": [bad]}, expect_error=True)


async def test_ledger_rejection_is_reported_as_tool_error(mcp_client):
    overspend = dict(TO_COLD, amount="5")
    text = await call(
        mcp_client, "add_transactions", {"transactions": [BUY, overspend]}, expect_error=True
    )
    assert "Not enough BTC" in text
    assert (await call(mcp_client, "list_transactions"))["total_matching"] == 0


async def test_update_and_delete(mcp_client):
    added = await call(mcp_client, "add_transactions", {"transactions": [BUY]})
    tx_id = added["created"][0]["id"]

    updated = await call(
        mcp_client, "update_transaction", {"transaction_id": tx_id, "cost_basis_usd": "400.00"}
    )
    assert Decimal(updated["cost_basis_usd"]) == Decimal("400.00")

    # Changing only the funding account fills in type/to from the existing tx
    updated = await call(
        mcp_client, "update_transaction", {"transaction_id": tx_id, "from_account": "Exchange USD"}
    )
    assert updated["from"] == "Exchange USD"

    sell = {"date": "2024-03-01T00:00:00Z", "type": "Sell", "amount": "0.005",
            "from_account": "Exchange BTC", "to_account": "Exchange USD",
            "proceeds_usd": "300.00", "fee_amount": "3.00", "fee_currency": "USD"}
    sell_id = (await call(mcp_client, "add_transactions", {"transactions": [sell]}))["created"][0]["id"]
    updated = await call(
        mcp_client, "update_transaction", {"transaction_id": sell_id, "proceeds_usd": "310.00"}
    )
    assert Decimal(updated["proceeds_usd"]) == Decimal("307.00")  # gross minus USD fee

    # The user's 1099-DA says basis was reported for this sale; then undo it
    updated = await call(
        mcp_client, "update_transaction", {"transaction_id": sell_id, "broker_reporting": "basis"}
    )
    assert updated["broker_reporting"] == "basis"
    updated = await call(
        mcp_client, "update_transaction", {"transaction_id": sell_id, "broker_reporting": "automatic"}
    )
    assert "broker_reporting" not in updated
    await call(mcp_client, "delete_transaction", {"transaction_id": sell_id})

    deleted = await call(mcp_client, "delete_transaction", {"transaction_id": tx_id})
    assert deleted["deleted"]["id"] == tx_id
    assert (await call(mcp_client, "list_transactions"))["total_matching"] == 0


async def test_recalculate_ledger(mcp_client):
    await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD]})
    out = await call(mcp_client, "recalculate_ledger")
    assert out["transactions"] == 2


async def test_review_ledger_lists_a_zero_basis_deposit(mcp_client, backend_db):
    """Read-only: a MyBTC deposit saved with $0 basis before v0.9.2 is listed."""
    from sqlalchemy import text

    added = await call(mcp_client, "add_transactions", {"transactions": [BUY]})
    assert added
    with backend_db.begin() as con:
        con.execute(text(
            "INSERT INTO transactions (type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, source, cost_basis_usd, is_locked)"
            " VALUES ('Deposit', '2024-02-01 12:00:00', 99, 2, '0.5', '0', 'BTC', 'MyBTC', '0', 0)"))
    out = await call(mcp_client, "review_ledger")
    assert out["read_only"] is True
    check = next(c for c in out["checks"] if c["key"] == "deposit_without_basis")
    assert check["count"] == 1 and check["items"][0]["source"] == "MyBTC"


async def test_a_transfer_fee_value_is_stored_or_taken_as_given(mcp_client):
    await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD, {
        **TO_COLD, "date": "2024-01-17T09:00:00Z", "from_account": "Wallet", "to_account": "Exchange BTC",
        "amount": "0.005", "fee_usd": "4.44"}]})
    transfers = (await call(mcp_client, "list_transactions", {"type": "Transfer"}))["transactions"]
    values = sorted(t["fee_usd"] for t in transfers)
    assert values == ["4.44", "5.00"]  # typed; 0.0001 x $50,000


async def test_list_filters_by_date_and_type(mcp_client):
    await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD]})
    only_jan_15 = await call(
        mcp_client, "list_transactions", {"start_date": "2024-01-15", "end_date": "2024-01-15"}
    )
    assert [t["type"] for t in only_jan_15["transactions"]] == ["Buy"]
    transfers = await call(mcp_client, "list_transactions", {"type": "Transfer"})
    assert transfers["total_matching"] == 1


async def test_portfolio_and_price(mcp_client):
    await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD]})
    portfolio = await call(mcp_client, "get_portfolio")
    balances = {b["account"]: b["balance"] for b in portfolio["balances"]}
    assert balances["Wallet"] > 0
    assert portfolio["btc_price_usd"] == 60000.0
    assert portfolio["tax_timezone"] == "UTC"

    price = await call(mcp_client, "get_btc_price", {"date": "2024-01-15"})
    assert price["usd"] == 50000.0


async def test_bad_login_is_a_clear_error(backend_db):
    btctx = BtctxClient(
        base_url="http://testserver", username="admin", password="wrong",
        transport=httpx.ASGITransport(app=app),
    )
    server.set_client(btctx)
    try:
        async with Client(server.mcp) as client:
            text = await call(client, "list_transactions", expect_error=True)
            assert "login failed" in text
    finally:
        server.set_client(None)
        await btctx.aclose()
