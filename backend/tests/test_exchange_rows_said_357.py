"""
The importer's words (#357, found writing B9's release tests): a row left
out alone reads "Row 9 is …", as two read "Rows 12 and 13 are …"; and a
file that isn't the chosen exchange's says so without a row number, as
River's does (the header is no row of the file's).
"""

import io
import re
from pathlib import Path

import pytest

from backend.services.exchange_cells import LeftOut, Reason
from backend.tests.conftest import stub_daily_prices

FILES = Path(__file__).resolve().parents[2] / "testdata" / "exchange_files"
SAMPLES = [("coinbase", "coinbase_2022.csv"), ("coinbase", "coinbase_2024.csv"), ("kraken", "kraken_ledgers.csv"),
           ("strike", "strike_activity.csv"), ("strike", "strike_statement.csv"),
           ("swan", "swan_deposits_and_purchases.csv"), ("swan-withdrawals", "swan_withdrawals.csv"),
           ("cash-app", "cash_app_activity.csv"), ("cash-app", "cash_app_bitcoin.csv")]
# A lone row's reason in the plural, as "Row 9 are …"
PLURAL_FOR_ONE = re.compile(r"^Row \d+ (are|aren't|move|trade|repeat|have|haven't|were|go) ")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture
def client(auth_client):
    r = auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code in (200, 204)
    return auth_client


def preview(client, mapping_id: str, name: str) -> dict:
    r = client.post("/api/import/exchange/preview", data={"mapping_id": mapping_id},
                    files={"file": (name, io.BytesIO((FILES / name).read_bytes()), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def test_a_reason_says_one_row_and_many_rows_each_their_way():
    left = LeftOut()
    left.add(Reason("are waiting, not completed", "is waiting, not completed"), 5)
    dollars = Reason("move dollars, not bitcoin", "moves dollars, not bitcoin")
    left.add(dollars, 2)
    left.add(dollars, 21)
    assert [w.message for w in left.warnings()] == ["Row 5 is waiting, not completed: left out.",
                                                    "Rows 2 and 21 move dollars, not bitcoin: left out."]


@pytest.mark.parametrize("mapping_id, name", SAMPLES)
def test_no_lone_row_is_said_in_the_plural(client, mapping_id, name):
    said = [w["message"] for w in preview(client, mapping_id, name)["warnings"]]
    assert not [message for message in said if PLURAL_FOR_ONE.match(message)], said


def test_the_lone_pending_copy_reads_as_one(client):
    said = [w["message"] for w in preview(client, "kraken", "kraken_ledgers.csv")["warnings"]]
    assert ("Row 9 is Kraken's pending copy of a deposit or withdrawal (no txid), whose completed row is read: "
            "left out.") in said


# River's activity file, which shares a column or two with others' headers
RIVER = (b"Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag\n"
         b"2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy\n")


@pytest.mark.parametrize("mapping_id", ["kraken", "coinbase", "strike", "swan", "cash-app"])
def test_a_wrong_files_error_names_no_row(client, mapping_id):
    r = client.post("/api/import/exchange/preview", data={"mapping_id": mapping_id},
                    files={"file": ("river.csv", io.BytesIO(RIVER), "text/csv")})
    [error] = r.json()["errors"]
    assert error["row_number"] == 0 and error["message"].startswith("This does not look like"), error
