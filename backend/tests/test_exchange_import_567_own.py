"""
The owner's own mapping, for any other exchange's file (B5b, #567): the
columns route shows a file's columns and the words in each, so the screen
can match them; a mapping is saved, listed, used, replaced and deleted, and
refused when it can't read the file or isn't one. Saved mappings are one
app_settings row (no migration), which a restore takes from the backup: a
mapping describes a file's columns, not this install (B5b's decision 7).

All rows are synthetic.
"""

import io
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.tests.conftest import stub_daily_prices
from backend.tests.test_restore_checks import OWNER, _backup, _restore, live  # noqa: F401  (live: fixture)

FILE = (
    "Exported by Example Exchange\n"
    "\n"
    "When,Type,Coins,Dollars,Charge,Charge In,Ref,State\n"
    "2025-04-01 09:00,Bought,0.01000000,\"1,010.00\",10.00,USD,r-1,done\n"
    "2025-04-02 09:00,Sold,0.00500000,495.00,5.00,USD,r-2,done\n"
    "2025-04-03 09:00,Withdrew,0.00200000,,0.00001000,BTC,r-3,done\n"
    "2025-04-04 09:00,Bought,0.01000000,\"1,010.00\",10.00,USD,r-4,waiting\n"
    "2025-04-05 09:00,Staked,0.00000500,,,,r-5,done\n"
    "2025-04-06 09:00,Card,,25.00,,,r-6,done\n"
).encode()

MAPPING = {
    "name": "Example Exchange",
    "columns": {"date": "When", "kind": "Type", "btc": "Coins", "usd": "Dollars", "fee": "Charge",
                "fee_currency": "Charge In", "row_id": "Ref", "status": "State"},
    "kinds": {"Bought": "buy", "Sold": "sell", "Withdrew": "send", "Staked": "reward"},
    "zone": "America/Chicago",
    "dollars_after_fee": ["buy", "sell"],
    "done": ["done"],
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture
def client(auth_client):
    r = auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code in (200, 204)
    for mapping in own(auth_client):
        auth_client.delete(f"/api/import/exchange/mappings/{mapping['id']}")
    yield auth_client
    for mapping in own(auth_client):
        auth_client.delete(f"/api/import/exchange/mappings/{mapping['id']}")


def own(client) -> list[dict]:
    r = client.get("/api/import/exchange/mappings")
    assert r.status_code == 200, r.text
    return [m for m in r.json()["mappings"] if not m["ready_made"]]


def upload(content: bytes = FILE) -> dict:
    return {"file": ("example.csv", io.BytesIO(content), "text/csv")}


def test_the_columns_route_shows_the_header_its_first_rows_and_each_columns_words(client):
    r = client.post("/api/import/exchange/columns", files=upload())
    assert r.status_code == 200, r.text
    found = r.json()
    assert found["header_row"] == 3
    assert found["columns"] == ["When", "Type", "Coins", "Dollars", "Charge", "Charge In", "Ref", "State"]
    assert found["samples"][0] == ["2025-04-01 09:00", "Bought", "0.01000000", "1,010.00", "10.00", "USD", "r-1", "done"]
    assert found["values"]["Type"] == ["Bought", "Sold", "Withdrew", "Staked", "Card"]
    assert found["values"]["State"] == ["done", "waiting"]
    assert found["looks_like"] is None


def test_a_mapping_previewed_unsaved_reads_the_file(client):
    r = client.post("/api/import/exchange/preview", data={"mapping": json.dumps(MAPPING)}, files=upload())
    assert r.status_code == 200, r.text
    answer = r.json()
    got = [(p["row_number"], p["type"], p["from_account"], p["to_account"], Decimal(p["amount"]),
            p["cost_basis_usd"] and Decimal(p["cost_basis_usd"]), p["proceeds_usd"] and Decimal(p["proceeds_usd"]),
            p["fee_amount"] and Decimal(p["fee_amount"]), p["date"][:19]) for p in answer["proposals"]]
    assert got == [
        # 1,010.00 paid with the fee in it: 1,000.00 bought the coins; 09:00 in Chicago (CDT) is 14:00 UTC
        (4, "Buy", "Bank", "Exchange BTC", Decimal("0.01"), Decimal("1000.00"), None, Decimal("10.00"),
         "2025-04-01T14:00:00"),
        # 495.00 arrived after the 5.00 fee: proceeds of 500.00
        (5, "Sell", "Exchange BTC", "Exchange USD", Decimal("0.005"), None, Decimal("500.00"), Decimal("5.00"),
         "2025-04-02T14:00:00"),
        (6, "Transfer", "Exchange BTC", "Wallet", Decimal("0.002"), None, None, Decimal("0.00001"),
         "2025-04-03T14:00:00"),
        (8, "Deposit", "External", "Exchange BTC", Decimal("0.000005"), Decimal("0.50"), None, None,
         "2025-04-05T14:00:00"),
    ]
    said = "\n".join(w["message"] for w in answer["warnings"])
    assert "Row 7 are waiting, not completed" in said
    assert "Row 9 are “Card”, a kind of row this mapping doesn't read" in said
    assert answer["total_rows"] == 6


def test_a_fee_is_bitcoin_only_when_the_file_says_so(client):
    """Without a currency column, a fee is dollars: a send's isn't read (a
    dollar fee read as bitcoin would be a fortune), and the warning says so."""
    mapping = {**MAPPING, "columns": {k: v for k, v in MAPPING["columns"].items() if k != "fee_currency"}}
    r = client.post("/api/import/exchange/preview", data={"mapping": json.dumps(mapping)}, files=upload())
    send = next(p for p in r.json()["proposals"] if p["type"] == "Transfer")
    assert send["fee_amount"] is None
    assert "This send's fee is 0.00001 USD: BitcoinTX records a send's fee in BTC" in "\n".join(
        w["message"] for w in r.json()["warnings"])
    buy = next(p for p in r.json()["proposals"] if p["type"] == "Buy")
    assert (buy["cost_basis_usd"], buy["fee_amount"]) == ("1000.00", "10.00")


def test_a_mapping_saved_is_listed_used_replaced_and_deleted(client):
    r = client.post("/api/import/exchange/mappings", json=MAPPING)
    assert r.status_code == 200, r.text
    saved = r.json()
    assert (saved["name"], saved["ready_made"], saved["mapping"]["columns"]["date"]) == ("Example Exchange", False, "When")
    assert [m["id"] for m in own(client)] == [saved["id"]]

    r = client.post("/api/import/exchange/preview", data={"mapping_id": saved["id"]}, files=upload())
    assert r.status_code == 200 and len(r.json()["proposals"]) == 4, r.text

    changed = {**MAPPING, "kinds": {**MAPPING["kinds"], "Card": "leave out"}}
    r = client.put(f"/api/import/exchange/mappings/{saved['id']}", json=changed)
    assert r.status_code == 200, r.text
    r = client.post("/api/import/exchange/preview", data={"mapping_id": saved["id"]}, files=upload())
    assert "Row 9 are “Card”, which this mapping leaves out" in "\n".join(w["message"] for w in r.json()["warnings"])

    assert client.delete(f"/api/import/exchange/mappings/{saved['id']}").status_code == 204
    assert own(client) == []
    r = client.post("/api/import/exchange/preview", data={"mapping_id": saved["id"]}, files=upload())
    assert r.status_code == 404


def test_a_deleted_mappings_id_is_never_given_again(client):
    first = client.post("/api/import/exchange/mappings", json=MAPPING).json()["id"]
    assert client.delete(f"/api/import/exchange/mappings/{first}").status_code == 204
    second = client.post("/api/import/exchange/mappings", json=MAPPING).json()["id"]
    assert second != first


def test_two_mappings_cant_share_a_name(client):
    assert client.post("/api/import/exchange/mappings", json=MAPPING).status_code == 200
    r = client.post("/api/import/exchange/mappings", json={**MAPPING, "name": "example exchange"})
    assert r.status_code == 409 and r.json()["detail"] == "A mapping of yours already has that name."


@pytest.mark.parametrize("change", [
    {"kinds": {"Bought": "purchase"}},
    {"kinds": {}},
    {"columns": {"date": "When", "kind": "Type"}},
    {"zone": "Mars/Olympus"},
    {"name": "   "},
    {"name": "x" * 61},
    {"accounts": {"to": "BTC Fees"}},
    {"columns": {**MAPPING["columns"], "to_account": "Wallet"}},
], ids=["an unknown kind", "no kinds", "no bitcoin column", "an unknown zone", "a blank name", "a long name",
        "an account named", "an account column"])
def test_a_mapping_that_isnt_one_is_refused(client, change):
    """No mapping holds an account: it says how to read a file, never where its rows go."""
    for request in (lambda body: client.post("/api/import/exchange/mappings", json=body),
                    lambda body: client.post("/api/import/exchange/preview", data={"mapping": json.dumps(body)},
                                             files=upload())):
        assert request({**MAPPING, **change}).status_code == 422
    assert own(client) == []


def test_a_mapping_naming_a_column_the_file_lacks_says_which(client):
    mapping = {**MAPPING, "columns": {**MAPPING["columns"], "status": "Condition"}}
    r = client.post("/api/import/exchange/preview", data={"mapping": json.dumps(mapping)}, files=upload())
    assert r.status_code == 200
    assert r.json()["proposals"] == []
    assert "Missing columns: Condition" in r.json()["errors"][0]["message"]


def test_no_more_than_fifty_mappings(client):
    for n in range(50):
        assert client.post("/api/import/exchange/mappings", json={**MAPPING, "name": f"Exchange {n}"}).status_code == 200
    r = client.post("/api/import/exchange/mappings", json={**MAPPING, "name": "One more"})
    assert r.status_code == 409


def test_a_restore_takes_the_backups_mappings(live, tmp_path):  # noqa: F811
    """This install's mappings go, the backup's come: a mapping describes a
    file's columns, and comes back with the rest of the backup's settings."""
    assert live.client.post("/api/import/exchange/mappings", json={**MAPPING, "name": "Made here"}).status_code == 200
    stored = json.dumps({"last_id": 7, "mappings": {"own-7": {**MAPPING, "name": "In the backup"}}})
    blob, _ = _backup(tmp_path, f"INSERT INTO app_settings (key, value) VALUES ('import_mappings', '{stored}')")
    assert _restore(live.client, blob).status_code == 200
    browser = TestClient(app)
    assert browser.post("/api/login", json=OWNER).status_code == 200
    assert [(m["id"], m["name"]) for m in own(browser)] == [("own-7", "In the backup")]
    assert browser.post("/api/import/exchange/mappings", json=MAPPING).json()["id"] == "own-8"
