"""
Chosen coins in the CSV, the reports, Ledger Review and the exchange
imports (#711, step C4 #732; docs/temp/2.0-coin-choice.md 6.3, 6.4, 6.6,
6.7; the owner's Q1).

- The CSV: three columns, `id` (the row's label in this file: the
  transaction's id where it was exported), `chosen_coins` (each acquisition
  by its row's id, "id 12: 0.01000000; id 30: 0.00500000") and
  `coins_chosen_at` (when the choice was saved, UTC). An export imports into
  an empty ledger with the same choices, whatever order its rows are in.
- The tax report's "Coins you chose": each transaction of the year with a
  choice, the coins chosen from each purchase (date acquired, BTC, cost) and
  the day the choice was saved, marked when after the coins left: the
  record the rule asks for (Treas. Reg. §1.1012-1(j)(2)).
- Ledger Review's reminder: choices saved on a later day than their coins left.
- River's and every exchange's import write no choice: a receive from a
  wallet says the coins leave oldest first and can be chosen afterwards.
"""

import csv
import io
import re
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from backend.models.transaction import Transaction
from backend.services.csv_import import CSV_COLUMNS, generate_template_csv, parse_csv_file
from backend.services.reports import transaction_history
from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.reporting_core import generate_report_data
from backend.services.review import build_review
from backend.tests.test_chosen_coins_711 import (  # noqa: F401  (owner, chose_a2: fixtures)
    EXCHANGE_BTC, WALLET, buy, chose_a2, coins, owner, pieces, saved, transfer,
)
from pypdf import PdfReader


def _rows_of(client) -> list[dict]:
    return list(csv.DictReader(io.StringIO(client.get("/api/backup/csv").text)))


def _file(rows: list[dict]) -> dict:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows({column: row.get(column, "") for column in CSV_COLUMNS} for row in rows)
    return {"file": ("import.csv", out.getvalue().encode(), "text/csv")}


def _delete_all(client) -> None:
    assert client.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204


def test_the_export_writes_each_rows_id_its_chosen_coins_and_when(chose_a2):  # noqa: F811
    ids = chose_a2.ids
    rows = {row["id"]: row for row in _rows_of(chose_a2)}
    assert rows[str(ids["S"])]["chosen_coins"] == f"id {ids['A2']}: 0.10010000"
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", rows[str(ids["S"])]["coins_chosen_at"])
    assert (rows[str(ids["A1"])]["chosen_coins"], rows[str(ids["A1"])]["coins_chosen_at"]) == ("", "")
    assert CSV_COLUMNS[-3:] == ["id", "chosen_coins", "coins_chosen_at"]


def test_an_export_imports_with_its_choice_and_its_day_in_any_row_order(chose_a2):  # noqa: F811
    """Rows reversed, and a row added by hand at the top with no id, so every
    id the import gives differs from the file's: the choice follows its
    label, never a position (6.3)."""
    ids = chose_a2.ids
    rows = _rows_of(chose_a2)
    chosen_at = next(r for r in rows if r["id"] == str(ids["S"]))["coins_chosen_at"]
    added = {"date": "2023-01-01T12:00:00Z", "type": "Deposit", "amount": "100", "from_account": "External",
             "to_account": "Bank", "source": "N/A"}
    _delete_all(chose_a2)
    r = chose_a2.post("/api/import/execute", files=_file([added, *reversed(rows)]))
    assert r.status_code == 200, r.text
    with chose_a2.Session() as db:
        spend = db.query(Transaction).filter(Transaction.type == "Withdrawal").one()
        newer = db.query(Transaction).filter(Transaction.type == "Deposit", Transaction.amount == 0.5).one()
        assert [(c.acquired_txn_id, f"{c.btc:.8f}") for c in spend.chosen_coins] == [(newer.id, "0.10010000")]
        assert newer.id != ids["A2"]
        assert spend.coins_chosen_at.strftime("%Y-%m-%dT%H:%M:%SZ") == chosen_at
    assert {piece[0] for piece in pieces(chose_a2, spend.id)} == {newer.id}


DEPOSIT = {"id": "7", "date": "2025-01-10T12:00:00Z", "type": "Deposit", "amount": "0.1", "from_account": "External",
           "to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "5000"}
SPEND = {"date": "2025-03-01T12:00:00Z", "type": "Withdrawal", "amount": "0.01", "from_account": "Wallet",
         "to_account": "External", "purpose": "Spent", "proceeds_usd": "900", "chosen_coins": "id 7: 0.01"}
CASH = {"id": "9", "date": "2025-01-05T12:00:00Z", "type": "Deposit", "amount": "100", "from_account": "External",
        "to_account": "Bank", "source": "N/A"}


@pytest.mark.parametrize("rows, row, column, said", [
    ([{**DEPOSIT, "id": "abc"}, SPEND], 2, "id", "id must be a whole number above 0, or blank"),
    ([{**DEPOSIT, "id": "0"}, SPEND], 2, "id", "id must be a whole number above 0, or blank"),
    ([{**DEPOSIT, "id": "1.5"}, SPEND], 2, "id", "id must be a whole number above 0, or blank"),
    ([DEPOSIT, {**SPEND, "id": "7"}], 3, "id", "id 7 is row 2's too: each row's id is its own"),
    ([DEPOSIT, {**SPEND, "chosen_coins": "id 8: 0.01"}], 3, "chosen_coins", "chosen_coins names id 8, which no row"),
    ([CASH, DEPOSIT, {**SPEND, "chosen_coins": "id 9: 0.01"}], 4, "chosen_coins",
     "chosen_coins names id 9 (row 2), which didn't acquire bitcoin"),
    ([DEPOSIT, {**SPEND, "chosen_coins": "7: 0.01"}], 3, "chosen_coins", "chosen_coins must read like"),
    ([DEPOSIT, {**SPEND, "chosen_coins": "id 7: lots"}], 3, "chosen_coins", "chosen_coins must read like"),
    ([DEPOSIT, {**SPEND, "chosen_coins": "id 7: 0.005; id 7: 0.005"}], 3, "chosen_coins", "names id 7 twice"),
    ([DEPOSIT, {**SPEND, "coins_chosen_at": "yesterday"}], 3, "coins_chosen_at", "coins_chosen_at must be"),
    # The review of #732: none of these may stop the import with an unexpected error
    ([{**DEPOSIT, "id": "\u00b2"}, SPEND], 2, "id", "id must be a whole number above 0, or blank"),
    ([{**DEPOSIT, "id": "9" * 5000}, SPEND], 2, "id", "id must be a whole number above 0, or blank"),
    ([DEPOSIT, {**SPEND, "chosen_coins": f"id {'9' * 5000}: 0.01"}], 3, "chosen_coins", "chosen_coins must read like"),
    ([DEPOSIT, {**SPEND, "chosen_coins": "id 7: 1e100"}], 3, "chosen_coins", "chosen_coins must read like"),
    ([DEPOSIT, {**SPEND, "chosen_coins": f"id 7: 1{'0' * 30}"}], 3, "chosen_coins", "chosen_coins must read like"),
    ([DEPOSIT, {**SPEND, "coins_chosen_at": "0001-01-01T00:00:00+01:00"}], 3, "coins_chosen_at", "from 2009-01-03"),
    ([DEPOSIT, {**SPEND, "coins_chosen_at": "0001-01-01T00:00:00Z"}], 3, "coins_chosen_at", "from 2009-01-03"),
    ([DEPOSIT, {**SPEND, "coins_chosen_at": "9999-12-31T23:59:59Z"}], 3, "coins_chosen_at", "from 2009-01-03"),
    # What the save would refuse, named at the preview
    ([DEPOSIT, {**SPEND, "chosen_coins": "id 7: 0.005"}], 3, "chosen_coins", "The coins chosen add up to 0.00500000"),
    ([DEPOSIT, {**DEPOSIT, "id": "", "date": "2025-02-01T12:00:00Z", "chosen_coins": "id 7: 0.1"}], 3, "chosen_coins",
     "Coins can be chosen only when they leave one of your wallets"),
    ([{**SPEND, "id": "3"}, {**DEPOSIT, "date": "2025-04-01T12:00:00Z"}], 2, "chosen_coins",
     "chosen_coins names id 7 (row 3), which isn't before this row"),
], ids=["not a number", "zero", "not whole", "shared", "no such row", "not an acquisition", "no id word",
        "no BTC", "twice", "bad moment", "not ascii", "too long", "too long in a choice", "huge BTC", "BTC past 21M",
        "year 1 abroad", "year 1", "year 9999", "short", "on a deposit", "acquired after"])
def test_a_choice_the_file_cant_hold_is_an_error_naming_the_row(owner, rows, row, column, said):  # noqa: F811
    _delete_all(owner)
    r = owner.post("/api/import/preview", files=_file(rows))
    assert r.status_code == 200, r.text
    errors = [(e["row_number"], e["column"], e["message"]) for e in r.json()["errors"]]
    assert any(e[:2] == (row, column) and said in e[2] for e in errors), errors


def test_a_choice_without_its_day_takes_the_imports(owner):  # noqa: F811
    _delete_all(owner)
    before = datetime.now(timezone.utc).replace(microsecond=0)
    r = owner.post("/api/import/execute", files=_file([DEPOSIT, SPEND]))
    assert r.status_code == 200, r.text
    with owner.Session() as db:
        spend = db.query(Transaction).filter(Transaction.type == "Withdrawal").one()
        assert spend.chosen_coins and spend.coins_chosen_at.replace(tzinfo=timezone.utc) >= before


def test_the_template_shows_ids_and_a_spend_of_chosen_coins():
    result = parse_csv_file(generate_template_csv().encode())
    assert not result.errors, result.errors
    rows = list(csv.DictReader(io.StringIO(generate_template_csv())))
    assert all(row["id"] for row in rows)
    [chosen] = [row for row in rows if row["chosen_coins"]]
    assert (chosen["type"], chosen["purpose"]) == ("Withdrawal", "Spent")


# The reports

def test_the_report_lists_the_coins_chosen_in_the_year(chose_a2):  # noqa: F811
    """The spend of 2025-06-01 chose 0.1001 of A2's coins (bought 2025-01-15,
    0.5 BTC for $45,000: $90,000 a BTC), its fee among them."""
    with chose_a2.Session() as db:
        [chosen] = generate_report_data(db, 2025)["coins_you_chose"]
        assert generate_report_data(db, 2023)["coins_you_chose"] == []
    assert {k: chosen[k] for k in ("date", "wallet", "kind", "btc", "chosen_later")} == {
        "date": "2025-06-01T12:00:00+00:00", "wallet": "Wallet", "kind": "Spent", "btc": 0.1001, "chosen_later": True}
    assert chosen["coins"] == [{"acquired": "2025-01-15", "btc": 0.1001, "cost": 9009.0}]
    assert re.fullmatch(r"\d{4}-\d\d-\d\d", chosen["chosen_on"])


def test_the_report_pdf_prints_them(chose_a2):  # noqa: F811
    with chose_a2.Session() as db:
        pdf = generate_comprehensive_tax_report(generate_report_data(db, 2025))
    words = " ".join(" ".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages).split())
    assert "Coins you chose" in words
    assert "A choice counts only if you made it by then and your records show it" in words


def test_the_transaction_history_marks_a_row_whose_coins_were_chosen(chose_a2):  # noqa: F811
    with chose_a2.Session() as db:
        lines = transaction_history.generate_transaction_history_report(db, 2025, "csv").decode().splitlines()
    rows = list(csv.DictReader(lines))
    [spend] = [row for row in rows if row["type"] == "Sell/Withdrawal"]
    assert spend["description"].endswith("coins chosen")
    assert not any("coins chosen" in row["description"] for row in rows if row is not spend)


# Ledger Review

def test_ledger_review_lists_the_choices_saved_after_the_coins_left(chose_a2):  # noqa: F811
    """A reminder, out of the total: the spend chose today, after 2025-06-01;
    a choice saved on its own day isn't listed."""
    ids = chose_a2.ids
    on_time = saved(chose_a2.post("/api/transactions", json=transfer("2025-07-01T12:00:00Z", "0.05",
                                                                    chosen=coins((ids["A2"], "0.05")))))
    with chose_a2.Session() as db:
        db.execute(text("UPDATE transactions SET coins_chosen_at = timestamp WHERE id = :id"), {"id": on_time})
        db.commit()
        review = build_review(db)
    [check] = [c for c in review["checks"] if c["key"] == "coins_chosen_later"]
    assert check["kind"] == "reminder" and check["count"] == 1
    assert [item["id"] for item in check["items"]] == [ids["S"]]
    assert "after the coins left on 2025-06-01" in check["items"][0]["issue"]
    assert "A choice counts only if you made it by then and your records show it." in " ".join(check["explanation"])


# The exchange imports write no choice (6.4)

RIVER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"


def _river(client, *rows: str) -> dict:
    files = {"file": ("river.csv", ("\n".join([RIVER, *rows]) + "\n").encode(), "text/csv")}
    r = client.post("/api/import/river/preview", files=files)
    assert r.status_code == 200, r.text
    return r.json()


def _ticked(answer: dict) -> list[dict]:
    keys = ("row_number", "date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd",
            "fee_amount", "fee_currency", "source", "purpose")
    return [{**{k: p[k] for k in keys}, "cost_basis_typed": "no" if p["basis_autofilled"] else None,
             "price_moment": p["price_moment"]} for p in answer["proposals"]]


def test_a_rivers_receive_takes_the_oldest_coins_and_can_be_chosen_afterwards(owner):  # noqa: F811
    answer = _river(owner, "2025-06-01 10:00:00,,,0.05000000,BTC,,,")
    [warning] = [w for w in answer["warnings"] if "oldest coins first" in w["message"]]
    assert warning["message"] == ("From your wallet, oldest coins first: you can choose the coins after the import.")
    r = owner.post("/api/import/river/execute", json={"rows": _ticked(answer)})
    assert r.status_code == 200, r.text
    with owner.Session() as db:
        moved = db.query(Transaction).filter(Transaction.type == "Transfer").one()
        assert moved.chosen_coins == []
    r = owner.put(f"/api/transactions/{moved.id}", json={"chosen_coins": coins((owner.ids["A2"], "0.05"))})
    assert r.status_code == 200, r.text
    assert r.json()["chosen_coins"] == [{"acquired_txn_id": owner.ids["A2"], "btc": "0.05000000"}]


def test_an_older_river_file_taking_chosen_coins_away_is_refused_whole(owner):  # noqa: F811
    """A Buy on the exchange dated before the transfer that brought B1's
    coins to the wallet: FIFO there then sends its coins instead, so the
    spend that chose B1's would lack them (#711's call (i), Q2)."""
    b1 = buy(owner, "2025-02-10T12:00:00Z", "0.1", "9000")
    saved(owner.post("/api/transactions", json=transfer("2025-02-11T12:00:00Z", "0.1", frm=EXCHANGE_BTC, to=WALLET)))
    s = saved(owner.post("/api/transactions", json={
        "type": "Withdrawal", "timestamp": "2025-03-01T12:00:00Z", "from_account_id": WALLET, "to_account_id": 99,
        "amount": "0.05", "fee_amount": "0", "fee_currency": "BTC", "purpose": "Spent", "proceeds_usd": "5000",
        "chosen_coins": coins((b1, "0.05"))}))
    before = owner.get("/api/transactions").json()
    answer = _river(owner, "2025-02-01 12:00:00,8000.00,USD,0.10000000,BTC,,,Buy")
    r = owner.post("/api/import/river/execute", json={"rows": _ticked(answer)})
    assert r.status_code == 400, r.text
    assert f"Transaction {s} " in r.json()["detail"] and "chose 0.05000000 BTC" in r.json()["detail"]
    assert owner.get("/api/transactions").json() == before
