"""
Every path that saves a transaction keeps its values within the API's limits
(schemas/transaction.py): a BTC value (and every amount) to 8 decimal places
and 10 digits before the point, a USD value to 2 and 16, finite numbers only.
The imports build their rows without the API's schema: a value they let
through was saved, and then the transaction list, the average cost and the
tax report failed for the whole ledger. The service checks every saved row
itself, and each import names the field in its own way: a row error in a
preview, a refusal in an execute, a 422 from the API.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import transaction as tx_service
from backend.services.csv_import import parse_csv_file
from backend.services.river_import import parse_river_csv
from backend.tests.conftest import stub_daily_prices

BANK, WALLET, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 2, 3, 4, 99
DATE = "2024-01-02T12:00:00Z"
ROUNDS_UP_USD = "9999999999999999.99"  # stored, 10000000000000000.00
ROUNDS_UP_AMOUNT = "9999999999.99999999"  # stored, 10000000000.00000000
READS = ("/api/transactions", "/api/calculations/average-cost-basis", "/api/reports/complete_tax_report?year=2024")


@pytest.fixture(autouse=True)
def empty_ledger(auth_client, monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 50000.0)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


@pytest.fixture
def ai(ai_key_headers):
    """A client with the AI key alone, as the connector calls."""
    client = TestClient(app)
    client.headers.update(ai_key_headers)
    return client


def every_read_works(client):
    for path in READS:
        r = client.get(path)
        assert r.status_code == 200, (path, r.text)


def usd_deposit(amount):
    return {"date": DATE, "type": "Deposit", "amount": amount, "from_account": "External", "to_account": "Bank"}


def mybtc_deposit(basis, amount="0.1"):
    return {"date": DATE, "type": "Deposit", "amount": amount, "from_account": "External", "to_account": "Wallet",
            "source": "MyBTC", "cost_basis_usd": basis}


def spend(**fields):
    return {"date": "2024-03-01T12:00:00Z", "type": "Withdrawal", "amount": "0.01", "from_account": "Wallet",
            "to_account": "External", "purpose": "Spent", "proceeds_usd": "500", "fee_amount": "0.0001",
            "fee_currency": "BTC", **fields}


@pytest.mark.parametrize("rows, field", [
    ([usd_deposit("1e20")], "amount"),
    ([mybtc_deposit("1e30")], "cost_basis_usd"),
    ([mybtc_deposit("1000"), spend(proceeds_usd="1e16")], "proceeds_usd"),
    ([mybtc_deposit("1000"), spend(fee_usd="1e20")], "fee_usd"),
    ([mybtc_deposit("1000"), spend(purpose="Gift", proceeds_usd=None, fmv_usd="1e20")], "fmv_usd"),
    ([mybtc_deposit("1000"), spend(fee_amount="1e11")], "fee_amount"),
    ([usd_deposit("1e999999999")], "amount"),
    ([usd_deposit("1E-999999999")], "amount"),
    ([mybtc_deposit(ROUNDS_UP_USD)], "cost_basis_usd"),
    ([usd_deposit(ROUNDS_UP_AMOUNT)], "amount"),
])
def test_the_ai_keys_import_refuses_a_value_too_large(auth_client, ai, rows, field):
    """With the AI key, a USD deposit of 1e20 and a basis of 1e30 were saved
    (200); every listing then failed with a server error."""
    rows = [{k: v for k, v in row.items() if v is not None} for row in rows]
    r = ai.post("/api/import/entries/execute", json={"rows": rows})
    assert r.status_code == 400, r.text
    assert field in r.text and "No transactions were saved" in r.text
    assert auth_client.get("/api/transactions").json() == []
    every_read_works(auth_client)

    result = ai.post("/api/import/entries/preview", json={"rows": rows}).json()["results"][-1]
    assert result["status"] == "invalid", result
    assert any(field in error for error in result["errors"]), result


# The largest values the database gives back within their rule, so they
# save and list. SQLite keeps the money columns as 64-bit floats, read back
# with the column's places: LARGEST_USD comes back as 9999999999999998.00,
# LARGEST_AMOUNT as 9999999999.99999809. One cent or one satoshi more
# (ROUNDS_UP_*) comes back as 10^16 or 10^10, past the rule, and is refused.
LARGEST_USD = "9999999999999998.99"
LARGEST_AMOUNT = "9999999999.99999904"


def test_the_largest_values_still_save_and_list(auth_client, ai):
    rows = [
        usd_deposit("9999999999.99"),
        mybtc_deposit(LARGEST_USD, amount="0.00000001"),
        mybtc_deposit("1", amount="21000000"),
        spend(proceeds_usd=LARGEST_USD, fee_usd=LARGEST_USD),
        spend(purpose="Gift", proceeds_usd=None, fee_amount=None, fee_currency=None, fmv_usd=LARGEST_USD),
        {"date": "2024-03-02T12:00:00Z", "type": "Transfer", "amount": "1", "from_account": "Wallet",
         "to_account": "Exchange BTC"},
        {"date": "2024-03-03T12:00:00Z", "type": "Sell", "amount": "1", "from_account": "Exchange BTC",
         "to_account": "Exchange USD", "proceeds_usd": LARGEST_USD, "fee_amount": LARGEST_AMOUNT,
         "fee_currency": "USD"},
    ]
    rows = [{k: v for k, v in row.items() if v is not None} for row in rows]
    r = ai.post("/api/import/entries/execute", json={"rows": rows})
    assert r.status_code == 200, r.text
    assert len(auth_client.get("/api/transactions").json()) == len(rows)
    every_read_works(auth_client)


CSV_HEADER = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose"


@pytest.mark.parametrize("row, column", [
    ("2024-01-02,Deposit,1e999,External,Bank,,,,,,", "amount"),
    ("2024-01-02,Deposit,100000000000,External,Bank,,,,,,", "amount"),
    ("2024-01-02,Deposit,1E-999999999,External,Bank,,,,,,", "amount"),
    ("2024-01-02,Deposit,0.1,External,Wallet,1e20,,,,MyBTC,", "cost_basis_usd"),
    ("2024-01-02,Transfer,0.1,Wallet,Exchange BTC,,,1e11,BTC,,", "fee_amount"),
    (f"2024-01-02,Deposit,0.1,External,Wallet,{ROUNDS_UP_USD},,,,MyBTC,", "cost_basis_usd"),
    (f"2024-01-02,Deposit,{ROUNDS_UP_AMOUNT},External,Bank,,,,,,", "amount"),
])
def test_a_csv_value_too_large_is_a_row_error_naming_its_column(auth_client, row, column):
    """A CSV amount of 1e999 passed the preview and the import, was stored
    as infinity, and the transaction list failed from then on."""
    result = parse_csv_file(f"{CSV_HEADER}\n{row}\n".encode())
    assert [e.column for e in result.errors] == [column], result.errors
    assert "digits before the decimal point" in result.errors[0].message
    assert not result.transactions

    r = auth_client.post("/api/import/preview", files={"file": ("import.csv", f"{CSV_HEADER}\n{row}\n", "text/csv")})
    assert r.status_code == 200 and r.json()["errors"][0]["column"] == column, r.text


RIVER_HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"


@pytest.mark.parametrize("row, column", [
    ("2026-02-01 09:00:00,,,1e999,BTC,,,Interest", "Received Amount"),
    ("2026-02-03 15:30:00,1e20,USD,0.0018,BTC,,,Buy", "Sent Amount"),
    ("2026-02-15 10:00:00,0.001,BTC,,,abc,BTC,", "Fee Amount"),
])
def test_a_river_number_out_of_its_limits_is_a_row_error(auth_client, row, column):
    """An Interest payout of 1e999 failed the River preview with a server
    error, and a fee that isn't a number was read as no fee."""
    rows, errors = parse_river_csv(f"{RIVER_HEADER}\n{row}\n".encode())
    assert rows == [] and [(e.row_number, e.column, e.severity) for e in errors] == [(2, column, "error")]

    r = auth_client.post("/api/import/river/preview", files={"file": ("river.csv", f"{RIVER_HEADER}\n{row}\n", "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["proposals"] == [] and r.json()["errors"][0]["column"] == column


@pytest.mark.parametrize("field, value", [
    ("fee_amount", "1e11"), ("amount", "1e999999999"), ("cost_basis_usd", "1e30"), ("fee_amount", "1E-999999999"),
])
def test_a_river_import_refuses_a_value_too_large(auth_client, field, value):
    row = {"date": DATE, "type": "Buy", "amount": "0.001", "from_account": "Exchange USD",
           "to_account": "Exchange BTC", "cost_basis_usd": "25.00", "fee_amount": "1", "fee_currency": "USD"}
    r = auth_client.post("/api/import/river/execute", json={"rows": [{**row, field: value}]})
    assert r.status_code == 400 and field in r.text, r.text
    assert auth_client.get("/api/transactions").json() == []


def test_a_river_transfer_with_its_fee_is_still_counted_with_the_fee(auth_client):
    """The fee is added to a Transfer's amount once the row is checked
    (BitcoinTX's amount includes the network fee; River's doesn't)."""
    deposit = {"date": DATE, "type": "Deposit", "amount": "1", "from_account": "External",
               "to_account": "Exchange BTC", "cost_basis_usd": "100", "source": "MyBTC"}
    move = {"date": "2024-02-01T12:00:00Z", "type": "Transfer", "amount": "0.5", "from_account": "Exchange BTC",
            "to_account": "Wallet", "fee_amount": "0.0001", "fee_currency": "BTC"}
    r = auth_client.post("/api/import/river/execute", json={"rows": [deposit, move]})
    assert r.status_code == 200, r.text
    moved = [t for t in auth_client.get("/api/transactions").json() if t["type"] == "Transfer"]
    assert [Decimal(t["amount"]) for t in moved] == [Decimal("0.5001")]


def api_deposit(**fields):
    return {"type": "Deposit", "timestamp": DATE, "from_account_id": EXTERNAL, "to_account_id": BANK,
            "amount": "100", "source": "N/A", **fields}


@pytest.mark.parametrize("amount, why", [
    ("1e999999999", "too large"), ("-1e999999999", "too large"), ("1e999998", "too large"),
    ("1E-999999999", "8 decimal places"),
])
def test_the_api_refuses_any_amount_out_of_its_limits(auth_client, amount, why):
    """1e999999999 was a server error, 1E-999999999 was saved as an amount of
    0, and 1e999998 took the server 16 seconds to refuse, with a message
    about converting integers."""
    r = auth_client.post("/api/transactions", json=api_deposit(amount=amount))
    assert r.status_code == 422 and why in r.text, r.text
    assert auth_client.get("/api/transactions").json() == []


@pytest.mark.parametrize("body, field", [
    (api_deposit(to_account_id=WALLET, amount="0.1", source="MyBTC", cost_basis_usd=ROUNDS_UP_USD), "cost_basis_usd"),
    (api_deposit(amount=ROUNDS_UP_AMOUNT), "amount"),
    ({"type": "Buy", "timestamp": DATE, "from_account_id": BANK, "to_account_id": EXCH_BTC, "amount": "0.1",
      "cost_basis_usd": "1000", "fee_amount": ROUNDS_UP_AMOUNT, "fee_currency": "USD"}, "fee_amount"),
])
def test_the_api_refuses_a_value_the_database_would_round_up(auth_client, body, field):
    """Within the schema's limits as typed, but stored as 10^16 (or 10^10),
    which the read refuses: saved, the whole list failed."""
    r = auth_client.post("/api/transactions", json=body)
    assert r.status_code == 422 and f"{field}: " in r.text and "too large" in r.text, r.text
    assert auth_client.get("/api/transactions").json() == []
    every_read_works(auth_client)


@pytest.mark.parametrize("field, value", [("fee_usd", "1e20"), ("amount", "1e999999999"), ("cost_basis_usd", "1e30")])
def test_an_edit_with_a_value_too_large_is_a_422(auth_client, field, value):
    created = auth_client.post("/api/transactions", json=api_deposit(
        to_account_id=WALLET, amount="0.1", cost_basis_usd="1000", source="MyBTC"))
    assert created.status_code == 200, created.text
    tx_id = created.json()["id"]
    spent = auth_client.post("/api/transactions", json={
        "type": "Withdrawal", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": WALLET,
        "to_account_id": EXTERNAL, "amount": "0.01", "purpose": "Spent", "proceeds_usd": "500",
        "fee_amount": "0.0001", "fee_currency": "BTC"})
    assert spent.status_code == 200, spent.text
    edited = spent.json()["id"] if field == "fee_usd" else tx_id
    r = auth_client.put(f"/api/transactions/{edited}", json={field: value})
    assert r.status_code == 422, r.text
    every_read_works(auth_client)


@pytest.mark.parametrize("field, value, to_account", [
    ("amount", Decimal("1e20"), BANK),
    ("amount", Decimal("Infinity"), BANK),
    ("amount", Decimal("NaN"), BANK),
    ("amount", "abc", BANK),
    ("cost_basis_usd", Decimal("1e16"), WALLET),
    ("fee_amount", Decimal("1e10"), BANK),
])
def test_the_service_checks_every_row_it_saves(test_db, field, value, to_account):
    """Every import and the API's create and edit pass here, whatever schema
    they come through."""
    data = {"type": "Deposit", "timestamp": datetime(2024, 1, 2, 12, tzinfo=timezone.utc), "from_account_id": EXTERNAL,
            "to_account_id": to_account,
            "amount": Decimal("1"), "source": "MyBTC", "cost_basis_usd": Decimal("10"), field: value}
    try:
        with pytest.raises(HTTPException) as refused:
            tx_service.create_transaction_record(data, test_db, auto_commit=False)
        assert refused.value.status_code == 422 and field in refused.value.detail, refused.value.detail
    finally:
        test_db.rollback()


def test_an_edit_is_checked_with_the_stored_values(auth_client, test_db):
    """An edit that leaves a stored value beyond the limits (saved before
    they were checked) says which one to correct."""
    created = auth_client.post("/api/transactions", json=api_deposit(
        to_account_id=WALLET, amount="0.1", cost_basis_usd="1000", source="MyBTC"))
    tx_id = created.json()["id"]
    test_db.query(tx_service.Transaction).filter_by(id=tx_id).update({"cost_basis_usd": Decimal("1e20")})
    test_db.commit()
    try:
        r = auth_client.put(f"/api/transactions/{tx_id}", json={"source": "Gift"})
        assert r.status_code == 422 and "cost_basis_usd" in r.text, r.text
        r = auth_client.put(f"/api/transactions/{tx_id}", json={"cost_basis_usd": "1000"})
        assert r.status_code == 200, r.text
    finally:
        test_db.rollback()


# #217's review
def test_a_basis_the_ledger_derives_past_the_limits_still_lists(auth_client):
    """A sale's basis is its lots' basis plus their fees: each within the
    limits as entered, the sum past them. The list shows it as it is."""
    buy = {"type": "Buy", "timestamp": DATE, "from_account_id": 1, "to_account_id": 4, "amount": "1",
           "cost_basis_usd": LARGEST_USD, "fee_amount": "9999999999", "fee_currency": "USD"}
    sell = {"type": "Sell", "timestamp": "2024-03-01T12:00:00Z", "from_account_id": 4, "to_account_id": 3,
            "amount": "1", "gross_proceeds_usd": "1", "fee_amount": "0", "fee_currency": "USD"}
    assert auth_client.post("/api/transactions", json=buy).status_code == 200
    r = auth_client.post("/api/transactions", json=sell)
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["cost_basis_usd"]) > Decimal("1e16")
    every_read_works(auth_client)


def test_a_value_stored_before_the_limits_still_lists(auth_client, test_db):
    from sqlalchemy import text

    r = auth_client.post("/api/transactions", json={
        "type": "Deposit", "timestamp": DATE, "from_account_id": 99, "to_account_id": 1, "amount": "1000",
        "fee_amount": "0", "fee_currency": "USD", "source": "N/A"})
    tx_id = r.json()["id"]
    test_db.execute(text("UPDATE transactions SET cost_basis_usd = 1e20 WHERE id = :i"), {"i": tx_id})
    test_db.commit()
    assert auth_client.get("/api/transactions").status_code == 200
    assert auth_client.get(f"/api/transactions/{tx_id}").status_code == 200


def test_a_zero_with_a_long_exponent_is_written_as_zero(ai):
    """A zero passes every limit, and the preview wrote its exponent out in full."""
    row = {**usd_deposit("1000"), "fee_amount": "0E-99999", "fee_currency": "USD"}
    r = ai.post("/api/import/entries/preview", json={"rows": [row]})
    assert r.status_code == 200 and len(r.content) < 10_000, len(r.content)
