"""
End-to-end tests: MCP client -> btctx_mcp server -> BitcoinTX FastAPI app
(in-process via ASGI transport) -> temporary SQLite database.

Run from the repo root:
    PYTHONPATH=$(pwd):$(pwd)/mcp_server pytest mcp_server/tests
"""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from mcp import Client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from backend.models.btc_price import BtcPriceHourly
from backend.services import ai_key, hourly_prices
from backend.services.bitcoin import get_current_price as _UNSTUBBED_CURRENT_PRICE  # the real one, before the stub
from backend.services.tax_time import set_tax_timezone
from backend.tests.conftest import init_test_db, stub_daily_prices
from btctx_mcp import server
from btctx_mcp.client import BtctxClient

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def backend_db(monkeypatch, tmp_path):
    # In a folder of its own: the AI copies made before the key's deletions
    # go to its backups folder, removed with it.
    path = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
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
    yield engine
    app.dependency_overrides.clear()
    engine.dispose()


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


async def test_ledger_guide_says_each_wallet_is_its_own_account():
    """2.0 (#357; 5.12, 5.14): the AI names accounts as get_portfolio lists
    them, and a wallet or exchange the user hasn't added is added by the
    user in Settings, never pooled into another account nor recorded as
    External, pointing to the README section that explains it."""
    from btctx_mcp.guide import LEDGER_GUIDE

    readme = (Path(__file__).parents[2] / "README.md").read_text()
    assert "## Wallets, exchanges and banks" in readme
    flat = " ".join(LEDGER_GUIDE.split())
    assert "get_portfolio" in flat and "accounts" in flat
    assert "A second wallet or exchange that isn't listed: the user adds it" in flat
    assert "Settings -> Wallets, exchanges and banks" in flat
    assert "github.com/DigiMonk73/BTCTX-MCP#wallets-exchanges-and-banks" in flat
    # The user's own wallet as External would make a move between their
    # own wallets a taxable withdrawal; pooling it would mix their lots
    assert "never as External" in flat
    for gone in ("pools it", "One wallet, one exchange", "one-wallet-one-exchange", "exchange by exchange"):
        assert gone not in flat, gone


async def test_ledger_guide_explains_a_past_year_confirm():
    """B6c's saved: false (#353): the AI shows the years and changes, and
    confirms only after the user's yes, never on its own."""
    from btctx_mcp.guide import LEDGER_GUIDE

    flat = " ".join(LEDGER_GUIDE.split())
    assert "saved: false" in flat
    for word in ("confirm", "confirm_move", "past_years"):
        assert word in flat, word
    assert "Never send a confirm the user didn't say yes to" in flat


async def test_ledger_guide_says_its_figures_are_not_tax_advice():
    """A tax question beyond the ledger gets the standard disclaimer's point
    and a pointer to the user's tax preparer (the owner's decision, 2026-10-10)."""
    from btctx_mcp.guide import LEDGER_GUIDE

    flat = " ".join(LEDGER_GUIDE.split())
    assert "a tax question beyond what the ledger shows" in flat
    assert "BitcoinTX's figures aren't tax advice and suggest their tax preparer" in flat


async def test_ledger_guide_maps_card_sats_back_to_rebate():
    """A rewards card's sats-back is a rebate, not income (#98): the guide
    once listed it under Reward, which BitcoinTX counts as income."""
    from btctx_mcp.guide import LEDGER_GUIDE
    from btctx_mcp.server import DepositSource

    flat = " ".join(LEDGER_GUIDE.split())
    assert "Reward = mining, staking, sign-up or referral bonuses." in flat
    assert "Rebate = bitcoin back for spending: a rewards card's sats-back" in flat and "Not Reward," in flat
    assert "sats-back, bonuses" not in flat
    assert "Rebate" in DepositSource.__args__
    # Card rewards on cash equivalents are income (#160)
    assert "Not Reward, except sats-back earned buying money orders or other cash equivalents: that isn't a " \
           "rebate but income (Reward)." in flat


async def test_ledger_guide_carries_the_tax_notes():
    """#160: what the AI tells the user of lost, donated and given coins,
    independent contractors' pay, a broker's dates and the Form 1040
    question."""
    from btctx_mcp.guide import LEDGER_GUIDE

    flat = " ".join(LEDGER_GUIDE.split())
    for note in (
        "paid to an independent contractor: Schedule C, and self-employment income, Schedule SE",
        "A theft or scam in an investment made for profit may be deductible on Form 4684, Section B, up to the "
        "coins' basis: suggest the user's tax preparer.",
        "the lower of value and basis for the rest (IRC 170(e)(1)(A)). Over $500 for the year's donations "
        "together it needs Form 8283; over $5,000, also a qualified appraisal (an exchange's price isn't one)",
        "gifts to one person other than a spouse over the year's annual exclusion ($19,000 in 2025 and 2026) "
        "generally need a gift tax return, Form 709",
        "A broker's 1099-DA may date a sale in UTC",
        "Form 1040's digital asset question is Yes in a year with a sale, a spend, a network fee paid in BTC, a "
        "gift or donation given, or BTC received as income, a reward, interest or a rebate",
    ):
        assert note in flat, note


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


async def test_a_duplicate_the_user_says_is_another_transaction_is_added(mcp_client):
    """#253 (D1): the per-row choice reaches the server, and saves the row."""
    await call(mcp_client, "add_transactions", {"transactions": [BUY]})
    preview = await call(mcp_client, "preview_transactions", {"transactions": [BUY]})
    assert preview["results"][0]["status"] == "duplicate"
    another = {**BUY, "not_a_duplicate_of": preview["results"][0]["matched_transaction_id"]}
    added = await call(mcp_client, "add_transactions", {"transactions": [another]})
    assert added["imported_count"] == 1 and added["skipped_duplicates"] == 0
    again = await call(mcp_client, "add_transactions", {"transactions": [another]})
    assert again["imported_count"] == 0 and again["skipped_duplicates"] == 1  # a retry saves it once


async def test_a_listed_spend_shows_its_gross_beside_its_after_fee_proceeds(mcp_client):
    """#157: a spend's proceeds_usd is after its network fee. Listed alone,
    an AI copying it back into update_transaction took the fee off again;
    the gross the user entered is listed beside it, and the guide says
    which one to send."""
    from btctx_mcp.guide import LEDGER_GUIDE

    spend = {
        "date": "2024-02-01T12:00:00Z", "type": "Withdrawal", "amount": "0.005",
        "from_account": "Exchange BTC", "to_account": "External", "purpose": "Spent",
        "proceeds_usd": "300.00", "fee_amount": "0.00001", "fee_currency": "BTC",
    }
    assert (await call(mcp_client, "add_transactions", {"transactions": [BUY, spend]}))["imported_count"] == 2
    listed = (await call(mcp_client, "list_transactions", {"type": "Withdrawal"}))["transactions"][0]
    # The fee: 0.00001 BTC x $50,000 = $0.50, off the $300 received
    assert (Decimal(listed["gross_proceeds_usd"]), Decimal(listed["proceeds_usd"])) == (
        Decimal("300.00"), Decimal("299.50"))
    await call(mcp_client, "update_transaction",
               {"transaction_id": listed["id"], "proceeds_usd": listed["gross_proceeds_usd"]})
    again = (await call(mcp_client, "list_transactions", {"type": "Withdrawal"}))["transactions"][0]
    assert Decimal(again["proceeds_usd"]) == Decimal("299.50")
    assert "send the new gross as proceeds_usd" in " ".join(LEDGER_GUIDE.split())
    # Changed into a gift, it has no proceeds: its old gross isn't listed as a value
    await call(mcp_client, "update_transaction", {"transaction_id": listed["id"], "purpose": "Gift"})
    gift = (await call(mcp_client, "list_transactions", {"type": "Withdrawal"}))["transactions"][0]
    assert "proceeds_usd" not in gift and "gross_proceeds_usd" not in gift


async def test_income_deposit_autofills_basis(mcp_client):
    dep = {
        "date": "2024-02-01", "type": "Deposit", "amount": "0.002",
        "from_account": "External", "to_account": "Wallet", "source": "Income",
    }
    res = (await call(mcp_client, "preview_transactions", {"transactions": [dep]}))["results"][0]
    assert res["autofilled_fields"] == ["cost_basis_usd"]
    assert Decimal(res["normalized"]["cost_basis_usd"]) == Decimal("100.00")


async def test_a_value_from_the_price_says_its_hour_and_source(mcp_client):
    """#208 (#145 plan 2.5): preview, add and list say which values BitcoinTX filled
    in from a price, and that price: its hour or day (here the day: no hourly
    price), where it came from and USD per BTC. A typed value says none."""
    dep = {
        "date": "2024-02-01", "type": "Deposit", "amount": "0.002",
        "from_account": "External", "to_account": "Wallet", "source": "Income",
    }
    priced = {"values": ["cost_basis_usd"], "at": "2024-02-01T00:00:00Z", "moment": "day", "source": "stub",
              "usd_per_btc": "50000.00"}
    preview = (await call(mcp_client, "preview_transactions", {"transactions": [dep]}))["results"][0]
    assert preview["simulated"]["from_price"] == priced
    added = await call(mcp_client, "add_transactions", {"transactions": [dep]})
    assert added["created"][0]["from_price"] == priced
    typed = dict(dep, date="2024-02-02", cost_basis_usd="99.00")
    added = await call(mcp_client, "add_transactions", {"transactions": [typed]})
    assert added["created"][0]["from_price"] is None
    newest, first = (await call(mcp_client, "list_transactions"))["transactions"]
    assert "from_price" not in newest
    assert first["from_price"] == priced


async def test_a_btc_fees_value_from_the_price_says_so(mcp_client):
    """A transfer's BTC fee valued at the price: the preview gives its value
    (simulated.fee_usd) and the price, and so do add and list (#208)."""
    preview = await call(mcp_client, "preview_transactions", {"transactions": [BUY, TO_COLD]})
    sim = preview["results"][1]["simulated"]
    assert Decimal(sim["fee_usd"]) == Decimal("5.00")  # 0.0001 BTC at the stub's $50,000
    assert sim["from_price"] == {"values": ["fee_usd"], "at": "2024-01-16T00:00:00Z", "moment": "day",
                                 "source": "stub", "usd_per_btc": "50000.00"}
    assert preview["results"][0]["simulated"]["from_price"] is None  # the Buy's values were given
    added = await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD]})
    assert [c["from_price"] and c["from_price"]["values"] for c in added["created"]] == [None, ["fee_usd"]]
    transfer = (await call(mcp_client, "list_transactions", {"type": "Transfer"}))["transactions"][0]
    assert transfer["from_price"]["values"] == ["fee_usd"]


async def test_a_value_moved_out_of_a_price_says_no_price(mcp_client):
    """Review of #324: an income moved to Bank keeps its "from the price" mark
    but not its value; from_price names a value only while it exists
    (transaction.values_from_price), in the update's answer and the list."""
    dep = {"date": "2024-02-01", "type": "Deposit", "amount": "0.002", "from_account": "External",
           "to_account": "Wallet", "source": "Income"}
    created = (await call(mcp_client, "add_transactions", {"transactions": [dep]}))["created"][0]
    assert created["from_price"]["values"] == ["cost_basis_usd"]
    moved = await call(mcp_client, "update_transaction",
                       {"transaction_id": created["id"], "to_account": "Bank", "amount": "100"})
    assert "from_price" not in moved, moved
    listed = (await call(mcp_client, "list_transactions"))["transactions"][0]
    assert "from_price" not in listed and "cost_basis_usd" not in listed


async def test_from_price_for_each_kind_of_value(mcp_client, backend_db):
    """The hour's price where there is one (the guide's main case), a Spent's
    gross proceeds, a gift's value and an inheritance's date of death (#208)."""
    hour = hourly_prices.hour_of(datetime(2024, 3, 1, 14, tzinfo=timezone.utc))
    with sessionmaker(bind=backend_db)() as db:
        db.add(BtcPriceHourly(hour=hour, usd=Decimal("50083.00"), source="bitstamp"))
        db.commit()
    rows = [
        {"date": "2024-03-01T14:30:00Z", "type": "Deposit", "amount": "0.1", "from_account": "External",
         "to_account": "Wallet", "source": "Income"},
        {"date": "2024-03-02T10:00:00Z", "type": "Withdrawal", "amount": "0.01", "from_account": "Wallet",
         "to_account": "External", "purpose": "Spent"},
        {"date": "2024-03-03T10:00:00Z", "type": "Withdrawal", "amount": "0.01", "from_account": "Wallet",
         "to_account": "External", "purpose": "Gift"},
        {"date": "2024-03-04T10:00:00Z", "type": "Deposit", "amount": "0.05", "from_account": "External",
         "to_account": "Wallet", "source": "Inherited", "acquired_at": "2023-06-15"},
    ]
    sims = [r["simulated"] for r in (await call(mcp_client, "preview_transactions", {"transactions": rows}))["results"]]
    income, spent, gift, inherited = (s["from_price"] for s in sims)
    assert income == {"values": ["cost_basis_usd"], "at": "2024-03-01T14:00:00Z", "moment": "hour",
                      "source": "bitstamp", "usd_per_btc": "50083.00"}
    assert Decimal(sims[0]["cost_basis_usd"]) == Decimal("5008.30")  # 0.1 BTC at the hour's $50,083.00
    assert (spent["values"], spent["moment"]) == (["gross_proceeds_usd"], "day")
    assert Decimal(sims[1]["gross_proceeds_usd"]) == Decimal("500.00")  # the value its from_price names
    assert (gift["values"], Decimal(sims[2]["fmv_usd"])) == (["fmv_usd"], Decimal("500.00"))
    assert (inherited["values"], inherited["at"], inherited["moment"]) == (
        ["cost_basis_usd"], "2023-06-15T00:00:00Z", "day")  # the date of death's day, not the deposit's
    added = (await call(mcp_client, "add_transactions", {"transactions": rows}))["created"]
    assert [c["from_price"] for c in added] == [income, spent, gift, inherited]
    listed = {t["id"]: t.get("from_price") for t in (await call(mcp_client, "list_transactions"))["transactions"]}
    assert [listed[c["id"]] for c in added] == [income, spent, gift, inherited]


async def test_portfolio_writes_a_few_sats_out(mcp_client):
    """#101, the review of #318: get_portfolio gave a 2-sat balance as 2e-08 (the
    balances route's numbers), beside the preview's "0.00000005"."""
    dep = {"date": "2024-02-01", "type": "Deposit", "amount": "0.00000005", "from_account": "External",
           "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "0.01"}
    spend = {"date": "2024-02-02", "type": "Withdrawal", "amount": "0.00000002", "from_account": "Wallet",
             "to_account": "External", "purpose": "Spent", "proceeds_usd": "0.01", "fee_amount": "0.00000001",
             "fee_currency": "BTC", "fee_usd": "0.01"}
    await call(mcp_client, "add_transactions", {"transactions": [dep, spend]})
    balances = {b["account"]: b["balance"] for b in (await call(mcp_client, "get_portfolio"))["balances"]}
    assert (balances["Wallet"], balances["Exchange BTC"]) == ("0.00000002", "0.00000000")
    assert balances["Bank"] == 0  # dollars as the API gives them


async def test_schema_rejects_unknown_account(mcp_client):
    bad = dict(BUY, to_account="Coldcard")
    await call(mcp_client, "preview_transactions", {"transactions": [bad]}, expect_error=True)


class RecordingTransport(httpx.ASGITransport):
    """The app's transport, noting the path of every request sent."""

    def __init__(self, app):
        super().__init__(app=app)
        self.paths: list[str] = []

    async def handle_async_request(self, request):
        self.paths.append(request.url.path)
        return await super().handle_async_request(request)


@pytest.mark.parametrize("tool, args", [
    ("add_transactions", {"transactions": [dict(BUY, amount="1e20")]}),
    ("add_transactions", {"transactions": [dict(BUY, cost_basis_usd="1e16")]}),
    ("preview_transactions", {"transactions": [dict(BUY, fee_amount="1e10")]}),
    ("add_transactions", {"transactions": [dict(TO_COLD, fee_usd="1e30")]}),
    ("update_transaction", {"transaction_id": 1, "proceeds_usd": "1e20"}),
    ("update_transaction", {"transaction_id": 1, "amount": "1e999999999"}),
])
async def test_a_value_too_large_is_refused_before_any_request(backend_db, tool, args):
    """A value over BitcoinTX's limits is a clear error from the connector
    itself: nothing is asked of BitcoinTX."""
    transport = RecordingTransport(app)
    btctx = BtctxClient(base_url="http://testserver", ai_key=make_ai_key(backend_db), transport=transport)
    server.set_client(btctx)
    try:
        async with Client(server.mcp) as client:
            text = await call(client, tool, args, expect_error=True)
        assert "should be less than" in text, text
        assert transport.paths == []
    finally:
        server.set_client(None)
        await btctx.aclose()


async def test_the_largest_values_pass_the_connector(mcp_client):
    deposit = {"date": "2024-01-15", "type": "Deposit", "amount": "9999999999.99", "from_account": "External",
               "to_account": "Bank"}
    assert (await call(mcp_client, "preview_transactions", {"transactions": [deposit]}))["ok"] is True
    gift = {"date": "2024-01-15", "type": "Deposit", "amount": "0.1", "from_account": "External",
            "to_account": "Wallet", "source": "Gift", "cost_basis_usd": "9999999999999998.99"}
    assert (await call(mcp_client, "preview_transactions", {"transactions": [gift]}))["ok"] is True


async def test_the_connectors_limits_are_bitcointxs():
    from backend.schemas.transaction import BTC_DIGITS, USD_DIGITS

    assert server.AMOUNT_LIMIT == Decimal(10) ** BTC_DIGITS
    assert server.USD_LIMIT == Decimal(10) ** USD_DIGITS


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


async def test_the_portfolio_says_why_there_is_no_live_price(mcp_client, monkeypatch):
    """Review of #191: with Nobody (or not chosen yet), the AI gets BitcoinTX's reason, not two nulls."""
    from backend.services import bitcoin, outbound

    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    monkeypatch.setattr(bitcoin, "get_current_price", _UNSTUBBED_CURRENT_PRICE)  # the app's own refusal
    portfolio = await call(mcp_client, "get_portfolio")
    assert portfolio["btc_price_usd"] is None and portfolio["btc_price_source"] is None
    assert "You chose Nobody for prices, so none is asked. To change that:" in portfolio["btc_price_unavailable"]


async def test_portfolio_and_price(mcp_client):
    await call(mcp_client, "add_transactions", {"transactions": [BUY, TO_COLD]})
    portfolio = await call(mcp_client, "get_portfolio")
    balances = {b["account"]: b["balance"] for b in portfolio["balances"]}
    assert balances["Wallet"] == "0.00990000"  # 0.01 left the exchange, 0.0001 of it the fee (#101: written out)
    assert portfolio["btc_price_usd"] == 60000.0
    assert "btc_price_source" in portfolio  # where the live price came from, when known (#145)
    assert "btc_price_unavailable" not in portfolio
    assert portfolio["tax_timezone"] == "UTC"

    price = await call(mcp_client, "get_btc_price", {"date": "2024-01-15"})
    assert price["usd"] == 50000.0 and price["source"] == "stub"  # where the stored price came from
    # a transaction's time: the price BitcoinTX values it at (the day's here: no hourly prices in tests)
    price = await call(mcp_client, "get_btc_price", {"date": "2024-01-15T21:05:00-05:00"})
    assert (price["usd"], price["moment"], price["priced_at"]) == (50000.0, "day", "2024-01-16T00:00:00Z")


async def test_a_time_without_an_offset_is_read_in_the_tax_timezone_as_add_transactions_reads_it(
        mcp_client, backend_db):
    """Review of #174: get_btc_price read it as UTC, add_transactions in the
    tax timezone: 21:05 in Chicago is the next UTC day."""
    tax_timezone(backend_db, "America/Chicago")
    price = await call(mcp_client, "get_btc_price", {"date": "2024-01-15T21:05:00"})
    assert price["priced_at"] == "2024-01-16T00:00:00Z"
    price = await call(mcp_client, "get_btc_price", {"date": "2024-01-15 21:05:00"})  # a space, too
    assert price["priced_at"] == "2024-01-16T00:00:00Z"


@pytest.mark.parametrize("name", ["America", "America/__init__/x"], ids=["a folder", "a module"])
async def test_a_tax_timezone_this_computer_cant_open_is_a_plain_error(monkeypatch, name):
    """#407: a 1.2.8 server kept a name only its own zone files opened; here
    a folder of zones failed with an OS error and, on Python 3.10 and 3.11, a
    module of tzdata with a TypeError, not the connector's own message."""
    async def answer(method, path, **kwargs):
        return {"timezone": name, "source": "setting"}

    monkeypatch.setattr(server, "_call", answer)
    with pytest.raises(server.ToolError, match=f"doesn't know the tax timezone {name};"):
        await server._tax_zone()


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


async def test_update_transaction_sets_and_clears_the_date_originally_acquired(mcp_client, backend_db):
    """#91: a My BTC deposit's date originally acquired, kept as the date given
    (#185: not a moment the tax timezone could move); "none" clears it."""
    tax_timezone(backend_db, "America/Chicago")
    deposit = {"date": "2025-04-01", "type": "Deposit", "amount": "0.1", "from_account": "External",
               "to_account": "Exchange BTC", "source": "MyBTC", "cost_basis_usd": "2000"}
    tx_id = (await call(mcp_client, "add_transactions", {"transactions": [deposit]}))["created"][0]["id"]
    updated = await call(mcp_client, "update_transaction", {"transaction_id": tx_id, "acquired_at": "2022-01-05"})
    assert updated["acquired_at"] == "2022-01-05"
    # 20:00 in Chicago is 02:00 UTC the next day: still January 5
    timed = await call(mcp_client, "update_transaction", {"transaction_id": tx_id, "acquired_at": "2022-01-05 20:00"})
    assert timed["acquired_at"] == "2022-01-05"
    cleared = await call(mcp_client, "update_transaction", {"transaction_id": tx_id, "acquired_at": "none"})
    assert "acquired_at" not in cleared


async def test_the_row_limit_reaches_the_ai(mcp_client):
    """The tool's description names the AI key's row limit, and a call over
    it comes back as BitcoinTX's error, saying what to do."""
    from backend.routers.entry_import import AI_MAX_ROWS

    tools = {t.name: t for t in (await mcp_client.list_tools()).tools}
    assert f"At most {AI_MAX_ROWS} rows a call" in tools["preview_transactions"].description
    rows = [dict(BUY, date=f"2024-01-{1 + i // 24:02d}T{i % 24:02d}:00:00Z") for i in range(AI_MAX_ROWS + 1)]
    for tool in ("preview_transactions", "add_transactions"):
        error = await call(mcp_client, tool, {"transactions": rows}, expect_error=True)
        assert f"BitcoinTX returned 400: Too many transactions. Maximum is {AI_MAX_ROWS} rows per request " \
               "with the AI key: send them in smaller groups, oldest first." in error, error
    assert (await call(mcp_client, "list_transactions"))["total_matching"] == 0


# The past-year warning (2.0 spec 5.8, 5.12; #353): a write that would change
# an earlier tax year's figures answers 409, which reaches the tool as its
# answer (saved: false, the years, the changes, the fingerprint); sent again
# with the fingerprint, it saves

OLD_DEPOSIT = {"date": "2023-12-01T12:00:00Z", "type": "Deposit", "amount": "0.01", "from_account": "External",
               "to_account": "Exchange BTC", "source": "MyBTC", "cost_basis_usd": "100.00"}
SALE_2025 = {"date": "2025-03-01T12:00:00Z", "type": "Sell", "amount": "0.005", "from_account": "Exchange BTC",
             "to_account": "Exchange USD", "proceeds_usd": "300.00"}
ASKED = {"saved", "detail", "years", "changes", "pending", "recalc_error", "exact", "why_not_exact", "timezone",
         "confirm", "to_confirm"}


@pytest.fixture
async def past_year_ledger(mcp_client, tax_year):
    """A 2024 buy and a 2025 sale from it; then this tax year is 2026."""
    created = (await call(mcp_client, "add_transactions", {"transactions": [BUY, SALE_2025]}))["created"]
    tax_year(2026)
    return {"buy": created[0]["id"], "sale": created[1]["id"]}


async def test_a_past_year_409_reaches_the_tool_and_its_confirm_saves(mcp_client, past_year_ledger):
    asked = await call(mcp_client, "add_transactions", {"transactions": [OLD_DEPOSIT]})
    assert set(asked) == ASKED
    assert asked["saved"] is False and re.fullmatch(r"[0-9a-f]{64}", asked["confirm"])
    assert asked["years"] == [2023, 2025] and asked["changes"] and asked["pending"] == []
    assert "add_transactions again with the same arguments and confirm" in asked["to_confirm"]
    assert (await call(mcp_client, "list_transactions"))["total_matching"] == 2  # nothing saved
    added = await call(mcp_client, "add_transactions", {"transactions": [OLD_DEPOSIT], "confirm": asked["confirm"]})
    assert added["imported_count"] == 1


async def test_the_preview_shows_the_past_years_the_add_asks_about(mcp_client, past_year_ledger):
    preview = await call(mcp_client, "preview_transactions", {"transactions": [OLD_DEPOSIT]})
    asked = await call(mcp_client, "add_transactions", {"transactions": [OLD_DEPOSIT]})
    assert (preview["past_years"]["years"], preview["past_years"]["confirm"]) == (asked["years"], asked["confirm"])
    this_year = dict(OLD_DEPOSIT, date="2026-03-01T12:00:00Z")
    assert (await call(mcp_client, "preview_transactions", {"transactions": [this_year]}))["past_years"] is None


async def test_update_transactions_confirm_move(mcp_client, past_year_ledger):
    change = {"transaction_id": past_year_ledger["buy"], "cost_basis_usd": "400.00"}
    asked = await call(mcp_client, "update_transaction", change)
    assert set(asked) == ASKED and asked["years"] == [2024, 2025]  # the lots it made, and the sale from them
    assert "update_transaction again with the same arguments and confirm_move" in asked["to_confirm"]
    updated = await call(mcp_client, "update_transaction", {**change, "confirm_move": asked["confirm"]})
    assert Decimal(updated["cost_basis_usd"]) == Decimal("400.00")


async def test_delete_transactions_confirm(mcp_client, past_year_ledger):
    asked = await call(mcp_client, "delete_transaction", {"transaction_id": past_year_ledger["sale"]})
    assert set(asked) == ASKED and asked["years"] == [2025]
    assert (await call(mcp_client, "list_transactions"))["total_matching"] == 2
    deleted = await call(mcp_client, "delete_transaction",
                         {"transaction_id": past_year_ledger["sale"], "confirm": asked["confirm"]})
    assert deleted["deleted"]["id"] == past_year_ledger["sale"]


async def test_recalculate_ledger_confirms_a_change_pending_in_an_earlier_year(mcp_client, backend_db,
                                                                              past_year_ledger):
    from sqlalchemy import text

    with backend_db.begin() as con:  # a stored figure a recalculation would put right
        con.execute(text("UPDATE transactions SET realized_gain_usd = '1.00' WHERE id = :i"),
                    {"i": past_year_ledger["sale"]})
    asked = await call(mcp_client, "recalculate_ledger")
    assert set(asked) == ASKED and asked["years"] == [2025] and asked["changes"] == []
    assert [item["id"] for item in asked["pending"]] == [past_year_ledger["sale"]]
    out = await call(mcp_client, "recalculate_ledger", {"confirm": asked["confirm"]})
    assert out["transactions"] == 2


async def test_each_request_waits_as_long_as_it_can_take():
    """1,200 s for the writes that can answer the past-year warning and the
    long reads (each can replay the whole ledger more than once: #352's
    measurement on the StartOS test VM; #637), 120 s for the rest."""
    waits = {}

    def answer(request):
        waits[(request.method, request.url.path)] = request.extensions["timeout"]["read"]
        return httpx.Response(200, json={})

    btctx = BtctxClient(base_url="http://testserver", ai_key="k", transport=httpx.MockTransport(answer))
    long, short = [("POST", "/api/import/entries/preview"), ("POST", "/api/import/entries/execute"),
                   ("POST", "/api/transactions"), ("PUT", "/api/transactions/5"),
                   ("DELETE", "/api/transactions/5"), ("POST", "/api/transactions/recalculate"),
                   ("GET", "/api/review")], [("GET", "/api/transactions"), ("GET", "/api/transactions/5"),
                                             ("GET", "/api/bitcoin/price"), ("POST", "/api/backup/ai-copy")]
    for method, path in long + short:
        await btctx.request(method, path)
    await btctx.aclose()
    assert waits == {**dict.fromkeys(long, 1200.0), **dict.fromkeys(short, 120.0)}


async def test_a_409_that_isnt_the_past_year_warning_stays_an_error():
    """Only the warning's 409 gives a fingerprint (`confirm`) and is a tool's
    answer; any other 409 (a refusal in plain words) is an error, as before."""
    btctx = BtctxClient(base_url="http://testserver", ai_key="k", transport=httpx.MockTransport(
        lambda request: httpx.Response(409, json={"detail": "Not saved: something else."})))
    server.set_client(btctx)
    try:
        with pytest.raises(server.ToolError, match="^BitcoinTX returned 409: Not saved: something else.$"):
            await server._write("POST", "/api/transactions/recalculate", None)
    finally:
        server.set_client(None)
        await btctx.aclose()
