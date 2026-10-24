"""
A second exchange's file into a ledger that already has rows (B5b, #567),
through #253's duplicate check with 5.11's refinement for multiple accounts:
what's already in the ledger is left out (the kind, the amount and the
minute), a row of the same amount within 48 hours is only similar (flagged,
imported by default), a recorded row in another account of the same kind
and currency on the same side never matches. The file goes only into the
exchange and wallet chosen; the new routes are the owner's alone.

The second exchange is one the owner added (B7a's gate takes any of
theirs). All rows are synthetic.
"""

import io
import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers.csv_import import MAX_FILE_SIZE
from backend.services import ai_key
from backend.tests.account_pairs import add_them
from backend.tests.conftest import default_login, stub_daily_prices

COLD, KRAKEN_USD, KRAKEN_BTC = 100, 102, 103
HEADER = ("Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,Fee BTC,BTC Price,"
          "Cost Basis (USD),Destination,Description,Transaction Hash,Note")
ROWS = [
    "a-1,Jan 06 2025 15:30:00,Purchase,-101.00,1.00,0.00100000,,,,,,,",  # recorded on this exchange
    "a-2,Jan 07 2025 10:00:00,Purchase,-50.50,0.50,0.00050000,,,,,,,",  # recorded on the other exchange
    "a-3,Jan 09 2025 12:00:00,Sale,19.80,0.20,-0.00020000,,,,,,,",  # recorded a day earlier: similar
    "a-4,Feb 12 2025 10:00:00,Send,,,-0.00030000,0.00000500,,,,,,",  # recorded, its fee in its amount
    "a-5,Feb 13 2025 10:00:00,Receive,,,0.00020000,,,,,,,",  # new
]
STRIKE_FILE = ("\n".join([HEADER, *ROWS]) + "\n").encode()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture
def client(fresh_app) -> TestClient:
    client = TestClient(app)
    assert client.post("/api/login", json=default_login()).status_code == 200
    add_them(client)
    return client


def upload(content: bytes = STRIKE_FILE) -> dict:
    return {"file": ("strike.csv", io.BytesIO(content), "text/csv")}


def preview(client, status=200, **form) -> dict:
    r = client.post("/api/import/exchange/preview", files=upload(), data={"mapping_id": "strike", **form})
    assert r.status_code == status, r.text
    return r.json()


def record(client, **tx) -> None:
    r = client.post("/api/transactions", json={"fee_amount": "0", **tx})
    assert r.status_code in (200, 201), r.text


def default_request(answer: dict) -> list[dict]:
    """The rows the screen sends with the preview's own ticks
    (riverImport.ts importRequestRows): the new and the similar of the same
    amount ticked, each in the ledger sent as left out."""
    keys = ("row_number", "date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd",
            "fee_amount", "fee_currency", "source", "purpose")
    out = []
    for p in answer["proposals"]:
        ticked = p["status"] == "new" or (p["status"] == "discrepancy" and not p["near_amount"])
        if ticked or p["status"] == "matched":
            found = {"matched_tx_id": p["matched_tx_id"]} if p["status"] == "matched" else {}
            out.append({**{k: p[k] for k in keys}, **found, "left_out": not ticked})
    return out


def test_a_second_exchanges_file_into_a_ledger_with_rows(client):
    record(client, type="Deposit", timestamp="2025-01-01T00:00:00Z", from_account_id=99, to_account_id=KRAKEN_BTC,
           amount="0.01", fee_currency="BTC", cost_basis_usd="1000.00", source="MyBTC")
    record(client, type="Buy", timestamp="2025-01-06T15:30:00Z", from_account_id=KRAKEN_USD, to_account_id=KRAKEN_BTC,
           amount="0.001", cost_basis_usd="100.00", fee_amount="1.00", fee_currency="USD")
    record(client, type="Buy", timestamp="2025-01-07T10:00:00Z", from_account_id=3, to_account_id=4,
           amount="0.0005", cost_basis_usd="50.00", fee_amount="0.50", fee_currency="USD")
    record(client, type="Sell", timestamp="2025-01-08T12:00:00Z", from_account_id=KRAKEN_BTC, to_account_id=KRAKEN_USD,
           amount="0.0002", proceeds_usd="20.00", fee_amount="0.20", fee_currency="USD")
    record(client, type="Transfer", timestamp="2025-02-12T10:00:00Z", from_account_id=KRAKEN_BTC, to_account_id=COLD,
           amount="0.000305", fee_amount="0.000005", fee_currency="BTC")

    answer = preview(client, exchange_account_id=KRAKEN_BTC, wallet_account_id=COLD)
    assert [(p["row_number"], p["type"], p["from_account"], p["to_account"], p["status"]) for p in answer["proposals"]] == [
        (2, "Buy", "Kraken USD", "Kraken BTC", "matched"),
        # The same buy on the first exchange is another buy (the owner's rule, 2026-10-15)
        (3, "Buy", "Kraken USD", "Kraken BTC", "new"),
        (4, "Sell", "Kraken BTC", "Kraken USD", "discrepancy"),
        (5, "Transfer", "Kraken BTC", "Cold Storage", "matched"),
        (6, "Transfer", "Cold Storage", "Kraken BTC", "new"),
    ]
    assert (answer["new_count"], answer["matched_count"], answer["discrepancy_count"]) == (2, 2, 1)
    assert "Same BTC amount as tx" in answer["proposals"][2]["discrepancy"]

    r = client.post("/api/import/exchange/execute", json={"rows": default_request(answer)})
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 3
    count = len(client.get("/api/transactions").json())

    # Imported again: every row is in the ledger, so the screen has none to send (River's answer)
    again = preview(client, exchange_account_id=KRAKEN_BTC, wallet_account_id=COLD)
    assert {p["status"] for p in again["proposals"]} == {"matched"}
    r = client.post("/api/import/exchange/execute", json={"rows": default_request(again)})
    assert r.status_code == 400 and r.json()["detail"] == "No rows to import.", r.text
    assert len(client.get("/api/transactions").json()) == count


def test_the_same_request_sent_twice_saves_its_rows_once(client):
    """The execute's double-submit guard, as River's (#253, #454)."""
    rows = default_request(preview(client, exchange_account_id=KRAKEN_BTC, wallet_account_id=COLD))
    assert client.post("/api/import/exchange/execute", json={"rows": rows}).json()["imported_count"] == len(rows)
    assert client.post("/api/import/exchange/execute", json={"rows": rows}).json()["imported_count"] == 0


@pytest.mark.parametrize("chosen, message", [
    ({"exchange_account_id": 5}, "Choose one of your exchanges."),  # a fee account
    ({"exchange_account_id": 6}, "Choose one of your exchanges."),
    ({"exchange_account_id": KRAKEN_USD}, "Choose one of your exchanges."),  # an exchange's dollars
    ({"exchange_account_id": 1}, "Choose one of your exchanges."),  # a bank
    ({"exchange_account_id": 999}, "Choose one of your exchanges."),
    ({"wallet_account_id": 5}, "Choose one of your wallets."),
    ({"wallet_account_id": 101}, "Choose one of your wallets."),  # a bank
    ({"wallet_account_id": KRAKEN_BTC}, "Choose one of your wallets."),
])
def test_a_file_goes_only_into_an_exchange_and_a_wallet(client, chosen, message):
    assert preview(client, status=422, **chosen)["detail"] == message


def test_a_hidden_account_is_never_chosen_for_the_owner(client):
    for first in (2, 4):
        assert client.put(f"/api/accounts/{first}", json={"hidden": True}).status_code == 200
    accounts = {(p["from_account"], p["to_account"]) for p in preview(client)["proposals"]}
    assert accounts == {("Kraken USD", "Kraken BTC"), ("Kraken BTC", "Kraken USD"), ("Kraken BTC", "Cold Storage"),
                        ("Cold Storage", "Kraken BTC")}


def test_a_row_sent_into_a_fee_account_is_refused(client):
    rows = default_request(preview(client, exchange_account_id=KRAKEN_BTC, wallet_account_id=COLD))
    rows[0]["to_account"] = "BTC Fees"
    r = client.post("/api/import/exchange/execute", json={"rows": rows})
    assert r.status_code == 400 and "Invalid account 'BTC Fees'" in r.json()["detail"]
    assert client.get("/api/transactions").json() == []


ROUTES = [
    ("GET", "/api/import/exchange/mappings", {}),
    ("POST", "/api/import/exchange/mappings", {"json": {}}),
    ("PUT", "/api/import/exchange/mappings/own-1", {"json": {}}),
    ("DELETE", "/api/import/exchange/mappings/own-1", {}),
    ("POST", "/api/import/exchange/columns", {"files": {"file": ("f.csv", b"a,b\n1,2\n", "text/csv")}}),
    ("POST", "/api/import/exchange/preview", {"files": {"file": ("f.csv", b"a,b\n1,2\n", "text/csv")},
                                              "data": {"mapping_id": "strike"}}),
    ("POST", "/api/import/exchange/execute", {"json": {"rows": []}}),
]


@pytest.mark.parametrize("method, path, kwargs", ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_the_ai_key_cant_import_a_file_or_change_a_mapping(auth_client, ai_key_headers, method, path, kwargs):
    r = TestClient(app).request(method, path, headers=ai_key_headers, **kwargs)
    assert r.status_code == 403 and r.json()["detail"] == ai_key.NOT_ALLOWED, r.text


@pytest.mark.parametrize("method, path, kwargs", ROUTES, ids=[f"{m} {p}" for m, p, _ in ROUTES])
def test_the_routes_need_a_login(auth_client, method, path, kwargs):
    assert TestClient(app).request(method, path, **kwargs).status_code == 401


@pytest.mark.parametrize("path", ["/api/import/exchange/preview", "/api/import/exchange/columns"])
def test_a_file_up_to_5_mb_is_read_and_a_larger_one_refused_in_words(auth_client, path):
    padding = b"\n" * (MAX_FILE_SIZE - len(STRIKE_FILE))  # blank rows: skipped
    data = {"mapping_id": "strike"} if path.endswith("preview") else {}
    r = auth_client.post(path, files={"file": ("big.csv", STRIKE_FILE + padding, "text/csv")}, data=data)
    assert r.status_code == 200, r.text[:300]
    r = auth_client.post(path, files={"file": ("big.csv", STRIKE_FILE + padding + b"x", "text/csv")}, data=data)
    assert r.status_code == 400 and r.json()["detail"] == "File too large. Maximum size is 5MB."


def test_a_mapping_that_isnt_text_is_refused(auth_client):
    """A JSON text can hold a lone surrogate, which can't be saved or said
    back (#313): the preview's error would quote the mapping's name."""
    mapping = json.dumps({"name": "NAME", "columns": {"date": "When", "kind": "Type", "btc": "Coins"},
                          "kinds": {"Bought": "buy"}}).replace("NAME", "\\ud800")
    r = auth_client.post("/api/import/exchange/preview", files=upload(), data={"mapping": mapping})
    assert r.status_code == 422 and "isn't text" in r.text, r.text
    r = auth_client.post("/api/import/exchange/mappings", content=mapping, headers={"Content-Type": "application/json"})
    assert r.status_code == 422, r.text
