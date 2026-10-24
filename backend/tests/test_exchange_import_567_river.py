"""
River's file through the importer for any exchange (B5b, #567, the owner's
decision 17): River's reader is the River mapping, and keeps River's rules
exactly. Every River file of River's own tests gives the same proposals,
counts, errors and warnings through the River mapping on the new route as on
River's own route, which stays (B6c's confirm and B7b's pickers use it).

All rows are synthetic.
"""

import io

import pytest

from backend.tests import test_river_by_book_350 as by_book
from backend.tests import test_river_import as river_tests
from backend.tests.conftest import stub_daily_prices

HEADER = river_tests.RIVER_HEADER
FILES = {
    "every pattern": river_tests.SYNTHETIC_ROWS,
    "B5a's rows": by_book.ROWS,
    "a row refused for its date, a number, an extra field, and one skipped": [
        "2024-01-01 10:00:00,100.00,USD,0.0025,BTC,,,Buy",
        "01/02/2024,100.00,USD,0.0025,BTC,,,Buy",
        "2024-01-03 10:00:00,abc,USD,0.0025,BTC,,,Buy",
        "2024-01-04 10:00:00,100.00,USD,0.0025,BTC,,,Buy,extra",
        "2024-01-05 10:00:00,1.00,EUR,2.00,GBP,,,",
    ],
    "unpatterned rows and missing amounts": [
        "2024-02-01 10:00:00,,USD,0.0025,BTC,,,Buy",
        "2024-02-02 10:00:00,0.001,BTC,,USD,0.10,USD,Sell",
        "2024-02-03 10:00:00,0,BTC,,,,,",
        "2024-02-04 10:00:00,,,0,BTC,,,",
        "2024-02-05 10:00:00,0.0005,BTC,55.00,USD,0.0001,BTC,Sell",
        "2024-02-06 10:00:00,100.00,USD,0.0012,BTC,1.00,BTC,Buy",
        "2024-02-07 10:00:00,0.001,BTC,,,1.00,USD,",
    ],
    "an empty file": [],
}


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


def river_file(rows: list[str]) -> bytes:
    return ("\n".join([HEADER, *rows]) + "\n").encode()


def preview(client, path: str, content: bytes, **form) -> dict:
    r = client.post(path, files={"file": ("river.csv", io.BytesIO(content), "text/csv")}, data=form)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("rows", FILES.values(), ids=FILES.keys())
def test_the_river_mapping_reads_a_file_as_rivers_own_route_does(auth_client, rows):
    content = river_file(rows)
    rivers = preview(auth_client, "/api/import/river/preview", content)
    mapped = preview(auth_client, "/api/import/exchange/preview", content, mapping_id="river")
    assert mapped == rivers


def test_a_file_that_isnt_rivers_is_said_so_by_both_routes(auth_client):
    content = b"Date,Amount\n2024-01-01 10:00:00,1\n"
    rivers = preview(auth_client, "/api/import/river/preview", content)
    mapped = preview(auth_client, "/api/import/exchange/preview", content, mapping_id="river")
    assert mapped == rivers
    assert "River" in mapped["errors"][0]["message"]


def test_the_river_mapping_is_listed_first_with_where_to_download_it(auth_client):
    r = auth_client.get("/api/import/exchange/mappings")
    assert r.status_code == 200, r.text
    first = r.json()["mappings"][0]
    assert (first["id"], first["name"], first["ready_made"], first["checked"]) == ("river", "River", True, True)
    assert "river.com" in first["help"]
    # The others come from their exchanges' published formats: the screen says to check their previews
    assert {m["id"]: m["checked"] for m in r.json()["mappings"][1:] if m["ready_made"]} == {
        "coinbase": False, "kraken": False, "strike": False, "swan": False, "swan-withdrawals": False,
        "cash-app": False}
