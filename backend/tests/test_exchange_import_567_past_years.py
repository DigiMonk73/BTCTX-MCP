"""
An exchange's file meets the past-year warning (B5b, #567; B6c's write, 2.0
spec 5.8): its preview names the earlier years its new rows are dated in,
and its import, River's, asks once for the file when it would change an
earlier year's figures, saves once confirmed, after a copy of the database,
and asks nothing when sent again. Only the rows its duplicate check keeps
count. The ledger is B6c's test ledger (a deposit in 2024, sales in 2024
and 2025, a deposit in 2026; this tax year 2026). All rows are synthetic.
"""

import io

from backend.migrate import PRE_CHANGE_KIND
from backend.tests.test_past_year_other_writes_353 import (  # noqa: F401  (ledger: a fixture)
    TAIL,
    copies,
    ledger,
    no_dry_run,
    stored,
)

HEADER = ("Reference,Date & Time (UTC),Transaction Type,Amount USD,Fee USD,Amount BTC,Fee BTC,BTC Price,"
          "Cost Basis (USD),Destination,Description,Transaction Hash,Note")
# An older lot: 2024's sale takes its coins first; 2025's still takes the 2024
# deposit's, at the same cost, so its figures stay
BACKDATED = "p-1,Dec 01 2023 12:00:00,Purchase,-505.00,5.00,0.01000000,,,,,,,"
THIS_YEAR = "p-2,Mar 05 2026 12:00:00,Purchase,-101.00,1.00,0.00100000,,,,,,,"


def preview(client, *rows: str) -> dict:
    data = ("\n".join([HEADER, *rows]) + "\n").encode()
    r = client.post("/api/import/exchange/preview", data={"mapping_id": "strike"},
                    files={"file": ("strike.csv", io.BytesIO(data), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def request(answer: dict) -> list[dict]:
    keys = ("row_number", "date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd",
            "fee_amount", "fee_currency", "source", "purpose")
    return [{k: p[k] for k in keys} for p in answer["proposals"]]


def execute(client, rows, confirm=None):
    return client.post("/api/import/exchange/execute", json={"rows": rows},
                       params={"confirm": confirm} if confirm else None)


def test_the_preview_names_the_earlier_years_its_new_rows_are_dated_in(ledger):
    client, _ = ledger
    assert preview(client, BACKDATED, THIS_YEAR)["past_years_dated"] == [2023]
    assert preview(client, THIS_YEAR)["past_years_dated"] == []


def test_a_file_that_changes_an_earlier_year_asks_once_and_its_confirm_saves_once(ledger):
    client, _ = ledger
    rows = request(preview(client, BACKDATED, THIS_YEAR))
    before = stored(client)
    asked = execute(client, rows)
    assert asked.status_code == 409, asked.text
    assert asked.json()["years"] == [2023, 2024]
    assert asked.json()["detail"] == f"This changes the figures of tax years 2023 and 2024, {TAIL}"
    assert stored(client) == before
    r = execute(client, rows, asked.json()["confirm"])
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == 2
    assert len(copies(client, PRE_CHANGE_KIND)) == 1
    again = execute(client, rows)  # a resend, or a second tab: nothing new, nothing asked
    assert again.status_code == 200 and again.json()["imported_count"] == 0, again.text


def test_a_file_dated_this_year_saves_at_once(ledger, monkeypatch):
    client, _ = ledger
    no_dry_run(monkeypatch)
    r = execute(client, request(preview(client, THIS_YEAR)))
    assert r.status_code == 200 and r.json()["imported_count"] == 1, r.text


def test_only_the_rows_the_duplicate_check_keeps_count(ledger, monkeypatch):
    """A backdated row already in the ledger asks nothing: it isn't saved."""
    client, _ = ledger
    rows = request(preview(client, BACKDATED))
    asked = execute(client, rows).json()
    assert execute(client, rows, asked["confirm"]).status_code == 200
    no_dry_run(monkeypatch)
    answer = preview(client, BACKDATED, THIS_YEAR)
    assert [p["status"] for p in answer["proposals"]] == ["matched", "new"]
    assert answer["past_years_dated"] == []
    sent = [{**row, "left_out": True, "matched_tx_id": p["matched_tx_id"]} if p["status"] == "matched" else row
            for row, p in zip(request(answer), answer["proposals"])]
    r = execute(client, sent)
    assert r.status_code == 200 and r.json()["imported_count"] == 1, r.text
