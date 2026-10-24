"""
The importer's edges (B5b, #567), from its fresh review: each test failed on
the code the review read. A number, a unit, a sign or an id the file can't
be sure of is refused or left out with its reason, never read as another
figure. All rows are synthetic.
"""

import io
import json
from decimal import Decimal

import pytest

from backend.services.exchange_cells import RowError, read_moment, read_number
from backend.tests.conftest import stub_daily_prices

HEADER = "When,Type,Coins,Dollars,Charge,Ref"
MAPPING = {
    "name": "Example Exchange",
    "columns": {"date": "When", "kind": "Type", "btc": "Coins", "usd": "Dollars", "fee": "Charge", "row_id": "Ref"},
    "kinds": {"Bought": "buy", "Sold": "sell", "Withdrew": "send", "Deposited": "receive", "Staked": "reward"},
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture
def client(auth_client):
    r = auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code in (200, 204)
    return auth_client


def preview(client, rows, mapping=None, header=HEADER, prefix=b"", mapping_id=None):
    content = prefix + ("\n".join([header, *rows]) + "\n").encode()
    data = {"mapping_id": mapping_id} if mapping_id else {"mapping": json.dumps(mapping or MAPPING)}
    r = client.post("/api/import/exchange/preview", data=data, files={"file": ("f.csv", io.BytesIO(content), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def said(answer) -> str:
    return "\n".join(p["message"] for p in answer["errors"] + answer["warnings"])


# B1: a comma read as a thousands separator in a bitcoin amount
@pytest.mark.parametrize("text", ["0,005", "0,123", "1,000", "12,345.5"])
def test_a_bitcoin_amount_takes_no_thousands_separator(text):
    with pytest.raises(RowError):
        read_number(text, column="Coins", bitcoin=True)


@pytest.mark.parametrize("text, decimal_comma", [("0,005", False), ("0.005", True), ("0,123.45", False)])
def test_a_thousands_group_never_starts_with_a_zero(text, decimal_comma):
    with pytest.raises(RowError):
        read_number(text, decimal_comma, "Dollars")


def test_a_send_of_0_comma_005_bitcoin_is_refused_never_5(client):
    answer = preview(client, ["2025-04-03 09:00,Withdrew,\"0,005\",,,r-1"])
    assert answer["proposals"] == [] and "Coins '0,005' isn't a number" in said(answer)


def test_with_a_decimal_comma_0_comma_005_is_half_a_hundredth(client):
    answer = preview(client, ["2025-04-03 09:00,Withdrew,\"0,005\",,,r-1"], {**MAPPING, "decimal_comma": True})
    assert Decimal(answer["proposals"][0]["amount"]) == Decimal("0.005")


# S1: a payout with no bitcoin
@pytest.mark.parametrize("coins", ["", "0"])
def test_a_payout_without_bitcoin_is_left_out_with_a_warning(client, coins):
    answer = preview(client, [f"2025-04-05 09:00,Staked,{coins},,,r-1"])
    assert answer["proposals"] == [] and "missing" in said(answer)


def test_coinbases_staking_row_without_an_amount_is_no_server_error(client):
    header = ("ID,Timestamp,Transaction Type,Asset,Quantity Transacted,Price Currency,Price at Transaction,Subtotal,"
              "Total (inclusive of fees and/or spread),Fees and/or Spread,Notes")
    answer = preview(client, ["a1,2025-02-04 10:00:00 UTC,Staking Income,BTC,,USD,,,,,"], header=header,
                     mapping_id="coinbase")
    assert answer["proposals"] == []


# S2: another currency than US dollars
@pytest.mark.parametrize("mapping_id, header, row", [
    ("coinbase", "Timestamp,Transaction Type,Asset,Quantity Transacted,Spot Price Currency,Spot Price at Transaction,"
                 "Subtotal,Total (inclusive of fees and/or spread),Fees and/or Spread,Notes",
     "2022-03-01T15:00:00Z,Buy,BTC,0.002,EUR,40000.00,80.00,81.99,1.99,Bought 0.002 BTC for €81.99 EUR"),
    ("cash-app", "Transaction ID,Date,Transaction Type,Currency,Amount,Fee,Net Amount,Asset Type,Asset Price,Asset Amount",
     "aaa001,2025-01-10 09:15:00 EST,Bitcoin Buy,GBP,-98.15,-2.00,-100.15,BTC,98150.00,0.001 BTC"),
])
def test_a_row_priced_in_another_currency_than_dollars_is_left_out(client, mapping_id, header, row):
    answer = preview(client, [row], header=header, mapping_id=mapping_id)
    assert answer["proposals"] == [] and "not US dollars" in said(answer)


# S3: a repeated row id
def test_a_row_with_an_earlier_rows_id_is_left_out_even_when_its_cells_differ(client):
    answer = preview(client, ["2025-04-01 09:00,Bought,0.01,1000.00,10.00,r-1",
                              "2025-04-01 09:00,Bought,0.01,1000.00,10.00,r-1",
                              "2025-04-02 09:00,Bought,0.02,2000.00,20.00,r-1"])
    assert [p["row_number"] for p in answer["proposals"]] == [2]
    assert "Row 3 repeat an earlier row" in said(answer)
    assert "Row 4 have the id of an earlier row" in said(answer)


# S4: a unit that contradicts its column
@pytest.mark.parametrize("row, expected", [
    ("2025-04-01 09:00,Bought,$5.00,1000.00,,r-1", "isn't bitcoin"),
    ("2025-04-01 09:00,Bought,0.01,0.5 BTC,,r-1", "isn't dollars"),
])
def test_a_unit_that_contradicts_its_column_is_refused(client, row, expected):
    answer = preview(client, [row])
    assert answer["proposals"] == [] and expected in said(answer)


def test_a_fee_cell_that_says_bitcoin_is_bitcoin(client):
    """A send's fee written "0.0001 BTC" in a fee column of dollars is the file saying so."""
    answer = preview(client, ["2025-04-03 09:00,Withdrew,0.002,,0.0001 BTC,r-1",
                              "2025-04-04 09:00,Bought,0.01,1000.00,0.0001 BTC,r-2"])
    send, buy = answer["proposals"]
    assert (Decimal(send["fee_amount"]), send["fee_currency"]) == (Decimal("0.0001"), "BTC")
    assert buy["fee_amount"] is None and "This buy's fee is 0.0001 BTC" in said(answer)


# S5: a sign that contradicts the row's kind
@pytest.mark.parametrize("mapping_id, header, row", [
    ("cash-app", "Transaction ID,Date,Transaction Type,Currency,Amount,Fee,Net Amount,Asset Type,Asset Price,Asset Amount",
     "aaa001,2025-01-10 09:15:00 EST,Bitcoin Buy,USD,$98.15,$0.00,$98.15,BTC,\"$98,150.00\",0.001 BTC"),
    ("strike", "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,Fee BTC,BTC Price,"
               "Cost Basis (USD),Destination,Description,Transaction Hash,Note",
     "s-1,Jan 06 2025 15:30:00,Purchase,-101.00,1.00,-0.00100000,,,,,,,"),
    ("strike", "Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,Fee BTC,BTC Price,"
               "Cost Basis (USD),Destination,Description,Transaction Hash,Note",
     "s-2,Feb 12 2025 10:00:00,Send,,,0.00030000,,,,,,,"),
])
def test_a_row_whose_money_goes_the_other_way_than_its_kind_is_left_out(client, mapping_id, header, row):
    answer = preview(client, [row], header=header, mapping_id=mapping_id)
    assert answer["proposals"] == [] and "go the other way" in said(answer)


# S6: what the checklist claimed and no test held
def test_a_byte_order_mark_is_no_part_of_the_first_column(client):
    answer = preview(client, ["2025-04-01 09:00,Bought,0.01,1000.00,10.00,r-1"], prefix=b"\xef\xbb\xbf")
    assert len(answer["proposals"]) == 1


def test_a_sends_bitcoin_with_its_fee_in_it(client):
    answer = preview(client, ["2025-04-03 09:00,Withdrew,0.002,,0.00001 BTC,r-1"], {**MAPPING, "send_fee_included": True})
    send = answer["proposals"][0]
    assert (Decimal(send["amount"]), Decimal(send["fee_amount"])) == (Decimal("0.00199"), Decimal("0.00001"))


def test_day_first_through_a_mapping(client):
    answer = preview(client, ["02/03/2025 09:00,Bought,0.01,1000.00,,r-1"], {**MAPPING, "day_first": True})
    assert answer["proposals"][0]["date"].startswith("2025-03-02T09:00")


def test_a_row_wider_than_the_header_is_refused(client):
    answer = preview(client, ["2025-04-01 09:00,Bought,0.01,1000.00,10.00,r-1,extra"])
    assert answer["proposals"] == [] and "more fields than the header" in said(answer)


def test_an_offset_after_a_space_is_read():
    assert read_moment("2025-01-15 10:00:00 +05:30", "UTC").isoformat() == "2025-01-15T04:30:00+00:00"
    assert read_moment("2025-01-15 10:00:00 -05", "UTC").isoformat() == "2025-01-15T15:00:00+00:00"
