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
from backend.services import ai_key
from backend.services.tax_time import set_tax_timezone
from backend.tests.conftest import init_test_db, stub_daily_prices
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

    async def fake_current():
        return {"USD": 60000.0}

    stub_daily_prices(monkeypatch, lambda day: 50000.0)
    monkeypatch.setattr("backend.services.bitcoin.get_current_price", fake_current)
    monkeypatch.setattr(
        "backend.services.transaction.get_btc_price", lambda timestamp, db: Decimal("50000")
    )
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()
    os.unlink(tmp.name)


def make_ai_key(engine) -> str:
    """What the owner does in Settings: turn AI access on, create a key."""
    db = sessionmaker(bind=engine)()
    try:
        ai_key.set_access(db, True)
        return ai_key.create_key(db)
    finally:
        db.close()


@pytest.fixture
async def mcp_client(backend_db):
    btctx = BtctxClient(
        base_url="http://testserver",
        ai_key=make_ai_key(backend_db),
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
        "recalculate_ledger", "review_ledger", "backup_ledger",
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


async def test_ledger_guide_says_a_second_wallet_is_pooled():
    """A user adding a second wallet or exchange through the AI hears that
    BitcoinTX pools it (#92), pointing to the README section that explains it."""
    from btctx_mcp.guide import LEDGER_GUIDE

    readme = (Path(__file__).parents[2] / "README.md").read_text()
    assert "## One wallet, one exchange" in readme
    flat = " ".join(LEDGER_GUIDE.split())
    assert "second wallet or a second exchange" in flat
    assert "pools it" in flat and '"One wallet, one exchange"' in flat
    assert "github.com/DigiMonk73/BTCTX-MCP#one-wallet-one-exchange" in flat
    # The user's own second wallet as External would make a move between
    # their own wallets a taxable withdrawal
    assert "Exchange BTC / Exchange USD, never External" in flat
    assert "untracked exchanges" not in flat


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


async def test_a_gift_changed_into_a_sell_is_on_form_8949(mcp_client, backend_db):
    """Bug hunt 2026-09-29: update_transaction(type="Sell") on a Gift kept
    purpose 'Gift' (the tool can't clear it), so Form 8949 left the sale out."""
    from backend.services.reports.form_8949 import build_form_8949_and_schedule_d

    gift = {"date": "2024-03-01T14:00:00Z", "type": "Withdrawal", "amount": "0.005",
            "from_account": "Exchange BTC", "to_account": "External", "purpose": "Gift"}
    created = (await call(mcp_client, "add_transactions", {"transactions": [BUY, gift]}))["created"]
    updated = await call(mcp_client, "update_transaction", {
        "transaction_id": created[1]["id"], "type": "Sell", "to_account": "Exchange USD",
        "proceeds_usd": "300.00"})
    assert updated["type"] == "Sell" and "purpose" not in updated
    with sessionmaker(bind=backend_db)() as db:
        rows = build_form_8949_and_schedule_d(2024, db)["short_term"]
    # basis: 0.005 of the buy's 420.00 + 4.20 fee
    assert [(str(r["proceeds"]), str(r["cost"])) for r in rows] == [("300.00", "212.10")]


async def test_a_fee_added_later_with_update_transaction_counts(mcp_client, backend_db):
    """Bug hunt 2026-09-29: add_transactions leaves fee_currency empty when
    there's no fee; update_transaction with fee_amount alone then stored a
    fee with no currency. A Sell's (USD) fee wasn't taken off its proceeds;
    a withdrawal's (BTC) fee left the balance with no disposal or fee_usd."""
    from sqlalchemy import text

    sell = {"date": "2024-03-01T00:00:00Z", "type": "Sell", "amount": "0.005",
            "from_account": "Exchange BTC", "to_account": "Exchange USD", "proceeds_usd": "300.00"}
    spend = {"date": "2024-03-02T00:00:00Z", "type": "Withdrawal", "amount": "0.004",
             "from_account": "Exchange BTC", "to_account": "External", "purpose": "Spent",
             "proceeds_usd": "200.00"}
    created = (await call(mcp_client, "add_transactions", {"transactions": [BUY, sell, spend]}))["created"]
    sell_id, spend_id = created[1]["id"], created[2]["id"]
    updated = await call(mcp_client, "update_transaction", {"transaction_id": sell_id, "fee_amount": "3.00"})
    assert (updated["proceeds_usd"], updated.get("fee_currency")) == ("297.00", "USD")
    updated = await call(mcp_client, "update_transaction", {"transaction_id": spend_id, "fee_amount": "0.0001"})
    assert (updated.get("fee_usd"), updated.get("fee_currency")) == ("5.00", "BTC")  # 0.0001 x $50,000
    with backend_db.connect() as con:
        fee_disposals = con.execute(text(
            "SELECT COUNT(*) FROM lot_disposals WHERE transaction_id = :i AND is_fee"), {"i": spend_id}).scalar()
        lots = con.execute(text("SELECT SUM(remaining_btc) FROM bitcoin_lots")).scalar()
    portfolio = await call(mcp_client, "get_portfolio")
    held = next(b["balance"] for b in portfolio["balances"] if b["account"] == "Exchange BTC")
    assert (fee_disposals, Decimal(str(lots)).quantize(Decimal("1E-8")), Decimal(str(held))) == \
        (1, Decimal("0.0009"), Decimal("0.0009"))  # 0.01 - 0.005 - 0.004 - 0.0001


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
            " fee_currency, source, cost_basis_usd)"
            " VALUES ('Deposit', '2024-02-01 12:00:00', 99, 2, '0.5', '0', 'BTC', 'MyBTC', '0')"))
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


def tax_timezone(engine, name):
    """What the owner does in Settings."""
    db = sessionmaker(bind=engine)()
    try:
        set_tax_timezone(db, name)
        db.commit()
    finally:
        db.close()


async def test_update_transaction_reads_dates_in_the_tax_timezone(mcp_client, backend_db):
    """Bug hunt 2026-09-29: update_transaction read a date without a timezone as
    UTC (a bare date as 00:00 UTC), while the guide and add_transactions read it
    in the tax timezone (a bare date is midday there). In Chicago a sale moved
    to "2025-01-01" was saved on Dec 31, 2024 at 6 pm there: the 2024 tax year."""
    tax_timezone(backend_db, "America/Chicago")
    tx_id = (await call(mcp_client, "add_transactions", {"transactions": [BUY]}))["created"][0]["id"]
    for given, stored in (
        ("2025-01-01", "2025-01-01T18:00:00Z"),           # midday in Chicago
        ("2024-12-31T21:00:00", "2025-01-01T03:00:00Z"),  # 9 pm Dec 31 in Chicago
        ("2024-12-31T21:00:00Z", "2024-12-31T21:00:00Z"),  # a stated timezone is kept
    ):
        updated = await call(mcp_client, "update_transaction", {"transaction_id": tx_id, "date": given})
        assert updated["date"] == stored, given


@pytest.mark.parametrize("given", [
    "2025-01-01", "2024-12-31T21:00:00", "2025-01-01T03:00:00.123Z", "2024-12-31T21:00:00-05:00",
    "2025-01-01 03:00:00 UTC", "01/02/2025", "01/02/2025 21:00:00",
])
async def test_update_transaction_reads_a_date_as_add_transactions_does(mcp_client, backend_db, given):
    """Bug hunt 2026-09-29: the same text is the same moment in both tools."""
    tax_timezone(backend_db, "America/Chicago")
    preview = await call(mcp_client, "preview_transactions", {"transactions": [dict(BUY, date=given)]})
    expected = preview["results"][0]["normalized"]["date"]
    tx_id = (await call(mcp_client, "add_transactions", {"transactions": [BUY]}))["created"][0]["id"]
    updated = await call(mcp_client, "update_transaction", {"transaction_id": tx_id, "date": given})
    assert updated["date"] == expected


async def test_list_transactions_days_are_in_the_tax_timezone(mcp_client, backend_db):
    """Bug hunt 2026-09-29: list_transactions filtered by UTC days, so a 9 pm
    Dec 31 buy in Chicago (03:00 UTC Jan 1) was missing from Dec 31 and listed
    under Jan 1."""
    tax_timezone(backend_db, "America/Chicago")
    await call(mcp_client, "add_transactions", {"transactions": [dict(BUY, date="2024-12-31T21:00:00")]})
    dec_31 = await call(mcp_client, "list_transactions", {"start_date": "2024-12-31", "end_date": "2024-12-31"})
    jan_1 = await call(mcp_client, "list_transactions", {"start_date": "2025-01-01", "end_date": "2025-01-01"})
    assert (dec_31["total_matching"], jan_1["total_matching"]) == (1, 0)


async def test_portfolio_and_price(mcp_client):
    await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD]})
    portfolio = await call(mcp_client, "get_portfolio")
    balances = {b["account"]: b["balance"] for b in portfolio["balances"]}
    assert balances["Wallet"] > 0
    assert portfolio["btc_price_usd"] == 60000.0
    assert portfolio["tax_timezone"] == "UTC"

    price = await call(mcp_client, "get_btc_price", {"date": "2024-01-15"})
    assert price["usd"] == 50000.0


async def test_wrong_key_is_a_clear_error(backend_db):
    make_ai_key(backend_db)
    btctx = BtctxClient(
        base_url="http://testserver", ai_key="btctx_ak_" + "x" * 43,
        transport=httpx.ASGITransport(app=app),
    )
    server.set_client(btctx)
    try:
        async with Client(server.mcp) as client:
            text = await call(client, "list_transactions", expect_error=True)
            assert "401" in text and "replaced or revoked" in text
            assert "x" * 43 not in text
    finally:
        server.set_client(None)
        await btctx.aclose()
