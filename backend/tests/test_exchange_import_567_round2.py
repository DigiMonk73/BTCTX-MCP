"""
The importer's edges from its fresh review's second round (B5b, #567): each
test failed on the code the review read. Kraken's ledger takes a line once
and reads its numbers as strictly as a mapping's; an amount too large, or a
merged row that can't be read, is a row's error, never a server error; a
negative bitcoin amount where coins come in is never a buy. All rows are
synthetic.
"""

import io
import json
from decimal import Decimal

import pytest

from backend.services.exchange_cells import RowError, read_number
from backend.tests.conftest import stub_daily_prices

KRAKEN = '"txid","refid","time","type","subtype","aclass","asset","wallet","amount","fee","balance"'
BUY_LINES = [
    '"L1","T1","2025-01-03 10:15:30","trade","tradespot","currency","USD","spot / main",-500.0000,1.3000,0',
    '"L2","T1","2025-01-03 10:15:30","trade","tradespot","currency","BTC","spot / main",0.0050000000,0,0',
]
STRIKE = ("Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,Fee BTC,BTC Price,"
          "Cost Basis (USD),Destination,Description,Transaction Hash,Note")
OWN = {
    "name": "Example Exchange",
    "columns": {"date": "When", "kind": "Type", "btc": "Coins", "usd": "Dollars"},
    "kinds": {"Bought": "buy", "Deposited": "receive", "Staked": "reward", "Withdrew": "send"},
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture
def client(auth_client):
    r = auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code in (200, 204)
    return auth_client


def preview(client, header, rows, mapping_id=None, mapping=None) -> dict:
    content = ("\n".join([header, *rows]) + "\n").encode()
    data = {"mapping_id": mapping_id} if mapping_id else {"mapping": json.dumps(mapping)}
    r = client.post("/api/import/exchange/preview", data=data, files={"file": ("f.csv", io.BytesIO(content), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def said(answer) -> str:
    return "\n".join(p["message"] for p in answer["errors"] + answer["warnings"])


def test_a_kraken_line_pasted_twice_is_read_once(client):
    """Overlapping exports joined: the trade is 0.005 BTC for $500, never doubled."""
    answer = preview(client, KRAKEN, [*BUY_LINES, *BUY_LINES], mapping_id="kraken")
    [buy] = answer["proposals"]
    assert (Decimal(buy["amount"]), Decimal(buy["cost_basis_usd"]), Decimal(buy["fee_amount"])) == (
        Decimal("0.005"), Decimal("500.00"), Decimal("1.30"))
    assert "Rows 4 and 5 repeat an earlier line (txid)" in said(answer)


@pytest.mark.parametrize("amount", ['"12,345"', '"$5.00"', '"0,005"'])
def test_a_kraken_bitcoin_line_is_read_strictly(client, amount):
    line = f'"L2","T1","2025-01-03 10:15:30","trade","tradespot","currency","BTC","spot / main",{amount},0,0'
    answer = preview(client, KRAKEN, [BUY_LINES[0], line], mapping_id="kraken")
    assert answer["proposals"] == [] and "isn't" in said(answer)


def test_kraken_reads_a_dollar_line_with_its_sign_and_unit():
    with pytest.raises(RowError):
        read_number("0.5 BTC", column="amount", unit="USD")


@pytest.mark.parametrize("header, rows, mapping_id", [
    (STRIKE, ["x,Jan 06 2025 15:30:00,Purchase,-101.00,1.00,0.001,,,,,,,",
              "x,Jan 06 2025 15:35:00,Purchase,,,abc,,,,,,,"], "strike"),
    (STRIKE, ["y,Jan 06 2025 15:30:00,Purchase,-101.00,1.00,123456789012345678901234567.5,,,,,,,"], "strike"),
    (KRAKEN, [BUY_LINES[0], BUY_LINES[1].replace("0.0050000000", "123456789012345678901234567.5")], "kraken"),
])
def test_an_unreadable_or_huge_amount_is_a_rows_error_never_a_server_error(client, header, rows, mapping_id):
    answer = preview(client, header, rows, mapping_id=mapping_id)
    assert answer["proposals"] == [] and answer["errors"]


def test_a_huge_dollar_amount_in_an_own_mapping_is_a_rows_error(client):
    answer = preview(client, "When,Type,Coins,Dollars", ["2025-04-01 09:00,Bought,0.01,123456789012345678901234567.5"],
                     mapping=OWN)
    assert answer["proposals"] == [] and answer["errors"]


@pytest.mark.parametrize("row", [
    "2025-04-01 09:00,Bought,-0.01,100.00",
    "2025-04-02 09:00,Deposited,-0.01,",
    "2025-04-03 09:00,Staked,-0.00001,",
])
def test_a_negative_bitcoin_amount_where_coins_come_in_is_left_out(client, row):
    """Whatever a file's signs mean, coins coming in are never negative: a reversal, never a second buy."""
    answer = preview(client, "When,Type,Coins,Dollars", [row], mapping=OWN)
    assert answer["proposals"] == [] and "go the other way" in said(answer)


def test_a_send_written_negative_is_still_a_send(client):
    answer = preview(client, "When,Type,Coins,Dollars", ["2025-04-03 09:00,Withdrew,-0.002,"], mapping=OWN)
    assert [p["type"] for p in answer["proposals"]] == ["Transfer"]


def test_unicode_digits_are_no_number():
    with pytest.raises(RowError):
        read_number("٠.٥", column="Coins")


def test_two_kind_words_alike_but_for_their_case_need_one_kind(client):
    mapping = {**OWN, "kinds": {"Buy": "buy", "BUY": "sell"}}
    r = client.post("/api/import/exchange/mappings", json=mapping)
    assert r.status_code == 422 and "the same word" in r.text


def test_an_own_mapping_cant_take_a_ready_made_ones_name(client):
    r = client.post("/api/import/exchange/mappings", json={**OWN, "name": "kraken"})
    assert r.status_code == 409 and r.json()["detail"] == "A ready-made mapping has that name."
