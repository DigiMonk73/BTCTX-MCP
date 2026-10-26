"""
The connector names the user's accounts as BitcoinTX lists them (spec 5.12;
card B5a #350): any bank, wallet or exchange account the server lists, by
its name now or a reserved name (Bank, Wallet, Exchange USD and Exchange
BTC always mean the first ones), or External. The list is read once per
run, again on a name it doesn't know, and again before an id is sent
(update_transaction, list_transactions' account filter), so a rename
meanwhile can't send a stale one. An unknown name is refused before any
request; a renamed account's reserved name is refused with its name now. A
BitcoinTX before 2.0 can't list them for the AI key (403, or 404): the
connector then takes 1.x's five names. Every request says it comes from a
2.0 connector (X-BitcoinTX-Connector), which a 1.x connector never sends.
"""

import json

import httpx
import pytest
from mcp import Client
from sqlalchemy.orm import sessionmaker

from backend.main import app
from backend.models.account import Account
from backend.services import account as account_service
from backend.services import ai_key
import btctx_mcp
from btctx_mcp import accounts, client as connector, server
from btctx_mcp.client import BtctxClient
from test_server import BUY, backend_db, call, make_ai_key  # noqa: F401  (fixture)

pytestmark = pytest.mark.anyio

UNKNOWN = ("Unknown account '{}'. The user's accounts: {}, and External. If it's a wallet or exchange they "
           "haven't added, ask them to add it in BitcoinTX (Settings, Wallets, exchanges and banks); never put it "
           "in another account.")
FIRST = "Bank, Wallet, Exchange USD, Exchange BTC"
DEPOSIT = {"date": "2024-01-10T12:00:00Z", "type": "Deposit", "amount": "0.01", "from_account": "External",
           "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "400"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


class Recording(httpx.AsyncBaseTransport):
    """The app in-process, every request noted (method, path, connector
    header); `answers` stands in for a server that answers a path its own way."""

    def __init__(self, answers: dict | None = None):
        self.inner = httpx.ASGITransport(app=app)
        self.answers = answers or {}
        self.seen: list[tuple[str, str, str | None]] = []
        self.sent: dict[str, bytes] = {}  # the last body sent to each path

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.seen.append((request.method, request.url.path, request.headers.get(connector.CONNECTOR_HEADER)))
        self.sent[request.url.path] = await request.aread()
        if request.url.path in self.answers:
            status, detail = self.answers[request.url.path]
            return httpx.Response(status, json={"detail": detail}, request=request)
        return await self.inner.handle_async_request(request)


def add(engine, kind: str, name: str) -> list[int]:
    with sessionmaker(bind=engine)() as db:
        return [a.id for a in account_service.add_account(db, kind, name)]


def rename(engine, account_id: int, name: str) -> None:
    with sessionmaker(bind=engine)() as db:
        db.get(Account, account_id).name = name
        db.commit()


async def connect(engine, transport: Recording):
    btctx = BtctxClient(base_url="http://testserver", ai_key=make_ai_key(engine), transport=transport)
    server.set_client(btctx)
    return btctx


@pytest.fixture
async def seen(backend_db):  # noqa: F811
    """A connector to BitcoinTX 2.0; yields its transport, and the MCP client as .mcp."""
    transport = Recording()
    btctx = await connect(backend_db, transport)
    async with Client(server.mcp) as client:
        transport.mcp = client
        yield transport
    server.set_client(None)
    await btctx.aclose()


def paths(transport: Recording, method: str | None = None) -> list[str]:
    return [path for m, path, _ in transport.seen if method in (None, m)]


async def test_an_account_name_is_any_text_in_the_tools_schemas(seen):
    tools = {t.name: t for t in (await seen.mcp.list_tools()).tools}
    row = tools["preview_transactions"].input_schema["$defs"]["TransactionInput"]["properties"]
    for schema in (row["from_account"], row["to_account"],
                   tools["update_transaction"].input_schema["properties"]["to_account"]["anyOf"][0],
                   tools["list_transactions"].input_schema["properties"]["account"]["anyOf"][0]):
        assert schema["type"] == "string" and "enum" not in schema
    assert row["to_account"]["description"] == ("One of the user's accounts, by name (get_portfolio lists them), "
                                                  "or External.")
    assert len(tools) == 12


async def test_rows_into_added_accounts_by_their_names(backend_db, seen):  # noqa: F811
    """The row goes to BitcoinTX with the account's name as it lists it."""
    assert add(backend_db, "wallet", "Cold Storage") == [100]
    added = await call(seen.mcp, "add_transactions", {"transactions": [dict(DEPOSIT, to_account="cold storage")]})
    assert added["imported_count"] == 1
    assert json.loads(seen.sent["/api/import/entries/execute"])["rows"][0]["to_account"] == "Cold Storage"
    listed = await call(seen.mcp, "list_transactions", {"account": "Cold Storage"})
    assert [(t["from"], t["to"]) for t in listed["transactions"]] == [("External", "Cold Storage")]


async def test_an_unknown_name_is_refused_before_any_request(seen):
    text = await call(seen.mcp, "preview_transactions",
                      {"transactions": [dict(DEPOSIT, to_account="Coldcard")]}, expect_error=True)
    assert text.endswith(UNKNOWN.format("Coldcard", FIRST))
    assert paths(seen, "POST") == []
    assert paths(seen).count("/api/accounts/") == 2  # read once, and again for the name it didn't know


async def test_the_list_is_read_once_then_again_on_a_name_it_doesnt_know(backend_db, seen):  # noqa: F811
    await call(seen.mcp, "preview_transactions", {"transactions": [DEPOSIT]})
    await call(seen.mcp, "preview_transactions", {"transactions": [DEPOSIT]})
    assert paths(seen).count("/api/accounts/") == 1
    add(backend_db, "wallet", "Jade")
    preview = await call(seen.mcp, "preview_transactions", {"transactions": [dict(DEPOSIT, to_account="jade")]})
    assert paths(seen).count("/api/accounts/") == 2
    # Sent by its name, as the server lists it
    assert json.loads(seen.sent["/api/import/entries/preview"])["rows"][0]["to_account"] == "Jade"
    assert preview["results"][0]["status"] == "ready", preview


async def test_an_id_is_sent_after_reading_the_list_again(backend_db, seen):  # noqa: F811
    """Jade deleted and added again between two calls: the id sent is the
    new Jade's, never the one read before."""
    await call(seen.mcp, "add_transactions", {"transactions": [DEPOSIT]})
    assert add(backend_db, "wallet", "Jade") == [100]
    tx = (await call(seen.mcp, "list_transactions", {"account": "Wallet"}))["transactions"][0]
    assert (await call(seen.mcp, "list_transactions", {"account": "Jade"}))["total_matching"] == 0
    with sessionmaker(bind=backend_db)() as db:
        account_service.delete_account(db, 100)
    assert add(backend_db, "wallet", "Jade") == [101]
    moved = await call(seen.mcp, "update_transaction", {"transaction_id": tx["id"], "type": "Deposit",
                                                         "from_account": "External", "to_account": "jade"})
    assert (moved["from"], moved["to"]) == ("External", "Jade")
    assert json.loads(seen.sent[f"/api/transactions/{tx['id']}"])["to_account_id"] == 101


async def test_a_renamed_accounts_reserved_name_is_refused_with_its_name_now(backend_db, seen):  # noqa: F811
    await call(seen.mcp, "list_transactions", {"account": "Wallet"})
    rename(backend_db, 2, "Coldcard")
    before = len(seen.seen)
    text = await call(seen.mcp, "list_transactions", {"account": "Wallet"}, expect_error=True)
    assert text.endswith("'Wallet' is now called 'Coldcard'. Use that name.")
    assert paths(seen)[before:] == ["/api/accounts/"]  # read again, then refused: no transactions asked for
    listed = await call(seen.mcp, "list_transactions", {"account": "coldcard"})
    assert listed["total_matching"] == 0


async def test_a_reserved_name_of_a_renamed_account_is_refused_in_rows(backend_db, seen):  # noqa: F811
    rename(backend_db, 4, "Coinbase BTC")
    text = await call(seen.mcp, "preview_transactions", {"transactions": [BUY]}, expect_error=True)
    assert text.endswith("'Exchange BTC' is now called 'Coinbase BTC'. Use that name.")
    assert paths(seen, "POST") == []


async def test_get_portfolio_lists_the_accounts(backend_db, seen):  # noqa: F811
    assert add(backend_db, "exchange", "Kraken") == [100, 101]
    with sessionmaker(bind=backend_db)() as db:
        account_service.change_account(db, 101, hidden=True)
    portfolio = await call(seen.mcp, "get_portfolio")
    assert portfolio["accounts"] == [
        {"id": 1, "name": "Bank", "kind": "bank", "currency": "USD", "exchange": None, "hidden": False},
        {"id": 2, "name": "Wallet", "kind": "wallet", "currency": "BTC", "exchange": None, "hidden": False},
        {"id": 3, "name": "Exchange USD", "kind": "exchange", "currency": "USD", "exchange": "Exchange",
         "hidden": False},
        {"id": 4, "name": "Exchange BTC", "kind": "exchange", "currency": "BTC", "exchange": "Exchange",
         "hidden": False},
        {"id": 100, "name": "Kraken USD", "kind": "exchange", "currency": "USD", "exchange": "Kraken",
         "hidden": True},
        {"id": 101, "name": "Kraken BTC", "kind": "exchange", "currency": "BTC", "exchange": "Kraken",
         "hidden": True},
    ]


@pytest.mark.parametrize("tool, args", [
    ("delete_transaction", {}), ("update_transaction", {"amount": "0.02"}),
])
async def test_the_names_are_read_before_a_write_never_after(seen, monkeypatch, tool, args):
    """A list that can't be read stops the tool before it changes anything,
    never after a write it then reports as failed (the review's finding)."""
    await call(seen.mcp, "add_transactions", {"transactions": [DEPOSIT]})
    tx = (await call(seen.mcp, "list_transactions"))["transactions"][0]
    monkeypatch.setattr(server, "_accounts", {"names": None})  # a new run
    seen.answers["/api/accounts/"] = (500, "down")
    await call(seen.mcp, tool, {"transaction_id": tx["id"], **args}, expect_error=True)
    assert [m for m, path, _ in seen.seen if path == f"/api/transactions/{tx['id']}" and m != "GET"] == []
    del seen.answers["/api/accounts/"]
    assert (await call(seen.mcp, "list_transactions"))["transactions"][0]["amount"] == tx["amount"]


async def test_every_request_says_it_is_a_2_0_connectors(seen):
    await call(seen.mcp, "get_portfolio")
    await call(seen.mcp, "preview_transactions", {"transactions": [DEPOSIT]})
    assert {header for _m, _p, header in seen.seen} == {btctx_mcp.__version__}


# A BitcoinTX before 2.0: its AI key can't read the list
@pytest.mark.parametrize("status", [403, 404])
async def test_a_1x_server_gets_1xs_five_names(backend_db, status):  # noqa: F811
    transport = Recording(answers={"/api/accounts/": (status, ai_key.NOT_ALLOWED)})
    btctx = await connect(backend_db, transport)
    try:
        async with Client(server.mcp) as client:
            preview = await call(client, "preview_transactions", {"transactions": [BUY, DEPOSIT]})
            assert preview["ready_count"] == 2
            text = await call(client, "preview_transactions", {"transactions": [dict(DEPOSIT, to_account="Jade")]},
                              expect_error=True)
            assert text.endswith("Unknown account 'Jade'. This BitcoinTX is older than 2.0 and has only these "
                                 "accounts: Bank, Wallet, Exchange USD, Exchange BTC, and External.")
            portfolio = await call(client, "get_portfolio")
            assert [(a["id"], a["name"]) for a in portfolio["accounts"]] == [
                (1, "Bank"), (2, "Wallet"), (3, "Exchange USD"), (4, "Exchange BTC")]
            listed = await call(client, "list_transactions", {"account": "Wallet"})
            assert listed["total_matching"] == 0
    finally:
        server.set_client(None)
        await btctx.aclose()


# Names compared as BitcoinTX compares them (5.1)
@pytest.mark.parametrize("name", [
    "Wallet", "wallet", "WALLET", "  Wallet  ", "Wal  let", "Wallet​", "⠀Wallet", "Wallet ",
    "Cold ❄️", "Köln", "Köln", "STRASSE", "straße", "Exchange　USD", "Ex­change",
])
def test_names_are_compared_as_bitcointx_compares_them(name):
    assert accounts.name_key(name) == account_service.name_key(name)


def test_the_characters_nothing_shows_are_bitcointxs():
    assert accounts.INVISIBLE == account_service.INVISIBLE
