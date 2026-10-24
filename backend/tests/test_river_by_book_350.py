"""
River's file into the exchange and wallet the owner chooses (spec 5.11, Q8;
card B5a #350). The preview takes `exchange_account_id` (an exchange's BTC
account) and `wallet_account_id` (a wallet); without them, the first
exchange and the first wallet, as 1.x had them, never a hidden one. Its
proposals use that exchange's two accounts and that wallet; a recurring buy
is paid from the first bank not hidden, and may be paid from any bank not
hidden or that exchange's dollars. Every name is the book's, and a file
into an added exchange or wallet imports (B7a's gate, #354).
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.river_import import adapt_river_rows, parse_river_csv
from backend.tests.account_pairs import COINBASE, add_them, rename
from backend.tests.conftest import default_login, stub_daily_prices

HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"
# Four recurring no-fee $25 buys (paid from a bank), a buy with a fee (paid
# from the exchange's dollars), a sale, a payout, a send and a receive
ROWS = [
    "2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy",
    "2026-01-12 12:00:00,25.00,USD,0.00031000,BTC,,,Buy",
    "2026-01-19 12:00:00,25.00,USD,0.00032000,BTC,,,Buy",
    "2026-01-26 12:00:00,25.00,USD,0.00033000,BTC,,,Buy",
    "2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy",
    "2026-02-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell",
    "2026-02-11 09:00:00,,,0.00002000,BTC,,,Interest",
    "2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,",
    "2026-03-01 10:00:00,,,0.00060000,BTC,,,",
]
# (type, from, to) of each row, in 1.x's accounts
IN_1X = [
    ("Buy", "Bank", "Exchange BTC"), ("Buy", "Bank", "Exchange BTC"), ("Buy", "Bank", "Exchange BTC"),
    ("Buy", "Bank", "Exchange BTC"), ("Buy", "Exchange USD", "Exchange BTC"), ("Sell", "Exchange BTC", "Exchange USD"),
    ("Deposit", "External", "Exchange BTC"), ("Transfer", "Exchange BTC", "Wallet"),
    ("Transfer", "Wallet", "Exchange BTC"),
]
# The same rows into Kraken and Cold Storage (account_pairs' ids)
INTO_KRAKEN = [(t, {"Exchange BTC": "Kraken BTC", "Exchange USD": "Kraken USD", "Wallet": "Cold Storage"}.get(f, f),
                {"Exchange BTC": "Kraken BTC", "Exchange USD": "Kraken USD", "Wallet": "Cold Storage"}.get(to, to))
               for t, f, to in IN_1X]
CHOOSE_EXCHANGE, CHOOSE_WALLET = "Choose one of your exchanges.", "Choose one of your wallets."


def river_file(*rows: str) -> dict:
    return {"file": ("river.csv", ("\n".join([HEADER, *rows]) + "\n").encode(), "text/csv")}


@pytest.fixture
def client(fresh_app, monkeypatch) -> TestClient:
    stub_daily_prices(monkeypatch, lambda day: 100000.0)
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    return client


def preview(client: TestClient, rows=ROWS, status=200, **chosen) -> dict:
    r = client.post("/api/import/river/preview", files=river_file(*rows), data={k: str(v) for k, v in chosen.items()})
    assert r.status_code == status, r.text
    return r.json()


def routes(answer: dict) -> list:
    return [(p["type"], p["from_account"], p["to_account"]) for p in answer["proposals"]]


def funding(answer: dict) -> list:
    return [p["funding_choices"] for p in answer["proposals"] if p["type"] == "Buy"][0]


def test_without_a_choice_a_file_goes_where_1x_put_it():
    parsed, errors = parse_river_csv(river_file(*ROWS)["file"][1])
    proposals, _errors, _warnings = adapt_river_rows(parsed)
    assert [(p.type, p.from_account, p.to_account) for p in proposals] == IN_1X
    assert proposals[0].funding_choices == ["Bank", "Exchange USD"]


def test_the_preview_without_a_choice_is_1xs(client):
    answer = preview(client)
    assert routes(answer) == IN_1X
    assert funding(answer) == ["Bank", "Exchange USD"]


def test_the_preview_names_the_accounts_as_they_are_called_now(fresh_app, client):
    rename(fresh_app, COINBASE)
    assert routes(preview(client))[5] == ("Sell", "Coinbase BTC", "Coinbase USD")


def test_a_file_into_a_chosen_exchange_and_wallet(client):
    add_them(client)
    answer = preview(client, exchange_account_id=103, wallet_account_id=100)
    assert routes(answer) == INTO_KRAKEN
    assert funding(answer) == ["Bank", "Credit Union", "Kraken USD"]


@pytest.mark.parametrize("chosen, message", [
    ({"exchange_account_id": 102}, CHOOSE_EXCHANGE),  # an exchange's dollars
    ({"exchange_account_id": 100}, CHOOSE_EXCHANGE),  # a wallet
    ({"exchange_account_id": 5}, CHOOSE_EXCHANGE),  # a fee account
    ({"exchange_account_id": 99}, CHOOSE_EXCHANGE),
    ({"exchange_account_id": 999}, CHOOSE_EXCHANGE),
    ({"wallet_account_id": 103}, CHOOSE_WALLET),  # an exchange's bitcoin
    ({"wallet_account_id": 1}, CHOOSE_WALLET),
    ({"wallet_account_id": 5}, CHOOSE_WALLET),
    ({"wallet_account_id": 999}, CHOOSE_WALLET),
])
def test_anything_but_an_exchange_and_a_wallet_is_refused(client, chosen, message):
    add_them(client)
    assert preview(client, status=422, **chosen)["detail"] == message


def test_a_hidden_account_is_never_a_default(client):
    add_them(client)
    for first in (1, 2, 4):  # the first bank, wallet and exchange (both its accounts)
        assert client.put(f"/api/accounts/{first}", json={"hidden": True}).status_code == 200
    answer = preview(client)
    assert routes(answer) == [(t, "Credit Union" if f == "Bank" else f, to) for t, f, to in INTO_KRAKEN]
    assert funding(answer) == ["Credit Union", "Kraken USD"]


def test_a_hidden_account_chosen_is_taken(client):
    add_them(client)
    assert client.put("/api/accounts/103", json={"hidden": True}).status_code == 200
    assert routes(preview(client, exchange_account_id=103, wallet_account_id=100)) == INTO_KRAKEN


def test_with_every_bank_hidden_a_recurring_buy_is_paid_from_the_exchange(client):
    assert client.put("/api/accounts/1", json={"hidden": True}).status_code == 200
    answer = preview(client)
    assert routes(answer)[:4] == [("Buy", "Exchange USD", "Exchange BTC")] * 4
    assert funding(answer) == ["Exchange USD"]


@pytest.mark.parametrize("hidden, message", [(2, CHOOSE_WALLET), (4, CHOOSE_EXCHANGE)])
def test_with_every_one_hidden_the_preview_needs_the_choice(client, hidden, message):
    assert client.put(f"/api/accounts/{hidden}", json={"hidden": True}).status_code == 200
    assert preview(client, status=422)["detail"] == message


def import_rows(answer: dict) -> list[dict]:
    """The preview's proposals as the screen sends them, each ticked."""
    keys = ("row_number", "date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd",
            "fee_amount", "fee_currency", "source", "purpose")
    return [{**{k: p[k] for k in keys}, "cost_basis_typed": "no" if p["basis_autofilled"] else None,
             "price_moment": p["price_moment"]} for p in answer["proposals"]]


def test_a_river_file_round_trip_into_kraken_and_cold_storage(client):
    """The save goes through the CSV import's checks by name; a send from
    Kraken BTC carries its network fee in its amount (Sent + Fee, #39)."""
    add_them(client)
    answer = preview(client, exchange_account_id=103, wallet_account_id=100)
    r = client.post("/api/import/river/execute", json={"rows": import_rows(answer)})
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == len(ROWS)
    saved = sorted(client.get("/api/transactions").json(), key=lambda t: t["timestamp"])
    assert {(t["type"], t["from_account_id"], t["to_account_id"]) for t in saved} == {
        ("Buy", 1, 103), ("Buy", 102, 103), ("Sell", 103, 102), ("Deposit", 99, 103), ("Transfer", 103, 100),
        ("Transfer", 100, 103)}
    send = next(t for t in saved if (t["type"], t["from_account_id"]) == ("Transfer", 103))
    assert (send["amount"], send["fee_amount"]) == ("0.00100500", "0.00000500")
    again = preview(client, exchange_account_id=103, wallet_account_id=100)
    assert {p["status"] for p in again["proposals"]} == {"matched"}
