"""
#951: rows of the AI connector's import that share a time are written in
the order given, as the CSV and exchange imports write a file's rows: the
order decides which lots a same-time disposal takes (first in, first
out). The AI route sorted them by type (Deposit, Buy, Transfer, Sell,
Withdrawal), so a Sell listed before a same-time Transfer out took the
coins the Transfer should have left behind.
"""

from decimal import Decimal

import pytest

CLIENT = None

WHEN = "2024-03-01T15:00:00Z"
HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes"


@pytest.fixture(autouse=True, scope="module")
def _set_client(auth_client):
    global CLIENT
    CLIENT = auth_client


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


BUYS = [
    {"date": "2024-01-01T15:00:00Z", "type": "Deposit", "amount": "40000", "from_account": "External",
     "to_account": "Bank", "source": "N/A"},
    {"date": "2024-01-02T15:00:00Z", "type": "Buy", "amount": "0.5", "from_account": "Bank",
     "to_account": "Exchange BTC", "cost_basis_usd": "10000"},
    {"date": "2024-01-03T15:00:00Z", "type": "Buy", "amount": "0.5", "from_account": "Bank",
     "to_account": "Exchange BTC", "cost_basis_usd": "30000"},
]
BUYS_CSV = ("2024-01-01T15:00:00Z,Deposit,40000,External,Bank,,,,,N/A,,\n"
            "2024-01-02T15:00:00Z,Buy,0.5,Bank,Exchange BTC,10000,,,,,,\n"
            "2024-01-03T15:00:00Z,Buy,0.5,Bank,Exchange BTC,30000,,,,,,\n")


def _two_buys():
    """0.5 BTC for $10,000, then 0.5 BTC for $30,000, on the exchange."""
    out = CLIENT.post("/api/import/entries/execute", json={"rows": BUYS})
    assert out.status_code == 200, out.text


SELL = {"date": WHEN, "type": "Sell", "amount": "0.5", "from_account": "Exchange BTC",
        "to_account": "Exchange USD", "proceeds_usd": "35000"}
MOVE = {"date": WHEN, "type": "Transfer", "amount": "0.5", "from_account": "Exchange BTC", "to_account": "Wallet"}


def _the_sell() -> dict:
    sells = [t for t in CLIENT.get("/api/transactions").json() if t["type"] == "Sell"]
    assert len(sells) == 1, sells
    return sells[0]


def test_a_sell_listed_before_a_same_time_transfer_takes_the_oldest_coins():
    _two_buys()
    out = CLIENT.post("/api/import/entries/execute", json={"rows": [SELL, MOVE]})
    assert out.status_code == 200, out.text
    sell = _the_sell()
    assert Decimal(str(sell["cost_basis_usd"])) == Decimal("10000")
    assert Decimal(str(sell["realized_gain_usd"])) == Decimal("25000")


def test_the_ai_import_and_the_csv_import_give_the_same_figures():
    """The same rows, in the same order, through each route (the CSV import
    takes only an empty ledger)."""
    file = (f"{HEADER}\n{BUYS_CSV}{WHEN},Sell,0.5,Exchange BTC,Exchange USD,,35000,,,,,\n"
            f"{WHEN},Transfer,0.5,Exchange BTC,Wallet,,,,,,,\n")
    out = CLIENT.post("/api/import/execute", files={"file": ("rows.csv", file.encode(), "text/csv")})
    assert out.status_code == 200, out.text
    by_csv = _the_sell()
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    assert CLIENT.post("/api/import/entries/execute", json={"rows": [*BUYS, SELL, MOVE]}).status_code == 200
    by_ai = _the_sell()
    assert Decimal(str(by_csv["cost_basis_usd"])) == Decimal("10000")
    for field in ("cost_basis_usd", "realized_gain_usd", "holding_period"):
        assert by_ai[field] == by_csv[field], field


def test_the_preview_shows_what_the_add_saves():
    _two_buys()
    out = CLIENT.post("/api/import/entries/preview", json={"rows": [SELL, MOVE]})
    assert out.status_code == 200, out.text
    sell = out.json()["results"][0]["simulated"]
    assert Decimal(sell["cost_basis_usd"]) == Decimal("10000")
    assert Decimal(sell["realized_gain_usd"]) == Decimal("25000")


def test_the_order_given_decides_when_the_transfer_comes_first():
    _two_buys()
    assert CLIENT.post("/api/import/entries/execute", json={"rows": [MOVE, SELL]}).status_code == 200
    assert Decimal(str(_the_sell()["cost_basis_usd"])) == Decimal("30000")


def test_a_buy_listed_after_a_same_time_sell_is_refused_as_the_csv_import_refuses_it():
    buy = {"date": WHEN, "type": "Buy", "amount": "0.5", "from_account": "Bank",
           "to_account": "Exchange BTC", "cost_basis_usd": "10000"}
    out = CLIENT.post("/api/import/entries/preview", json={"rows": [SELL, buy]})
    assert out.status_code == 200, out.text
    assert out.json()["results"][0]["status"] == "rejected", out.json()["results"][0]
    assert CLIENT.post("/api/import/entries/execute", json={"rows": [SELL, buy]}).status_code == 400
    assert CLIENT.get("/api/transactions").json() == []
    file = f"{HEADER}\n{WHEN},Sell,0.5,Exchange BTC,Exchange USD,,35000,,,,,\n{WHEN},Buy,0.5,Bank,Exchange BTC,10000,,,,,,\n"
    assert CLIENT.post("/api/import/execute", files={"file": ("rows.csv", file.encode(), "text/csv")}).status_code != 200
    assert CLIENT.get("/api/transactions").json() == []
