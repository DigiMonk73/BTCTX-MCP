"""
Ledger Review's check of values priced at the day (#144, PR 4;
services/hourly_review.py): what the price of their hour would change, by
tax year (in the tax timezone), changes of $1.00 or more listed, all of
them in the year's totals; typed values never listed; nothing changes
until the owner applies by item or by year (login only), after a backup
copy, and then the values are at the hour, marked so, and recalculated.
"""

from decimal import Decimal
from pathlib import Path

import pytest

from backend.services import hourly_prices
from backend.tests.conftest import stub_daily_prices, stub_prices_at

BANK, WALLET, EXCHANGE_BTC, EXTERNAL = 1, 2, 4, 99
D = Decimal
DAY_PRICE, HOUR_PRICE = 30000, 40000


def post(client, **fields) -> dict:
    r = client.post("/api/transactions", json=fields)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def ledger(auth_client, monkeypatch):
    """Values priced at the day's $30,000, before hourly prices: an income
    deposit, a spend with its fee, a transfer fee late on 31 December in New
    York (1 January UTC), a tiny reward; a typed income value; and an
    inheritance (valued at its date of death's day by rule, #173). Then the
    hours' price is $40,000."""
    auth_client.delete("/api/transactions/delete_all")
    assert auth_client.put("/api/settings/tax-timezone", json={"timezone": "America/New_York"}).status_code == 200
    stub_daily_prices(monkeypatch, lambda day: DAY_PRICE)
    stub_prices_at(monkeypatch, lambda when: DAY_PRICE, moment="day")
    post(auth_client, type="Buy", timestamp="2024-06-01T10:00:00Z", from_account_id=BANK, to_account_id=EXCHANGE_BTC,
         amount="1", fee_amount="0", fee_currency="USD", cost_basis_usd="40000")
    deposit = dict(type="Deposit", from_account_id=EXTERNAL, to_account_id=WALLET, fee_amount="0", fee_currency="BTC")
    rows = {
        "income": post(auth_client, **deposit, timestamp="2025-03-01T14:47:00Z", amount="0.1", source="Reward"),
        "spend": post(auth_client, type="Withdrawal", timestamp="2025-06-01T10:20:00Z", from_account_id=EXCHANGE_BTC,
                      to_account_id=EXTERNAL, amount="0.05", fee_amount="0.0001", fee_currency="BTC",
                      purpose="Spent"),
        "transfer": post(auth_client, type="Transfer", timestamp="2025-01-01T04:30:00Z", from_account_id=EXCHANGE_BTC,
                         to_account_id=WALLET, amount="0.1", fee_amount="0.0002", fee_currency="BTC"),
        "tiny": post(auth_client, **deposit, timestamp="2025-04-01T09:00:00Z", amount="0.00001", source="Income"),
        "typed": post(auth_client, **deposit, timestamp="2025-05-01T09:00:00Z", amount="0.1", source="Income",
                      cost_basis_usd="999"),
        "inherited": post(auth_client, **deposit, timestamp="2025-02-01T09:00:00Z", amount="0.1", source="Inherited",
                          acquired_at="2024-12-01T15:00:00Z"),
    }
    monkeypatch.setattr(hourly_prices, "hourly_price", lambda db, when, wait=True: (D(HOUR_PRICE), "bitstamp"))
    yield {k: v["id"] for k, v in rows.items()}
    auth_client.put("/api/settings/tax-timezone", json={"timezone": "UTC"})
    auth_client.delete("/api/transactions/delete_all")


def check(client) -> dict:
    return next(c for c in client.get("/api/review").json()["checks"] if c["key"] == "day_priced_values")


def tx(client, tx_id) -> dict:
    return client.get(f"/api/transactions/{tx_id}").json()


def test_values_priced_at_the_day_are_listed_by_tax_year_with_what_moves(auth_client, ledger):
    found = check(auth_client)
    assert [i["id"] for i in found["items"]] == [ledger["transfer"], ledger["income"], ledger["spend"]]
    by_id = {i["id"]: i for i in found["items"]}
    assert by_id[ledger["income"]]["change"] == "Income and basis $3000.00 -> $4000.00."
    assert by_id[ledger["spend"]]["change"] == "Proceeds $1500.00 -> $2000.00; Fee value $3.00 -> $4.00."
    assert by_id[ledger["transfer"]]["year"] == 2024  # 31 December in New York
    assert "the price when its hour began (14:00 UTC)" in by_id[ledger["income"]]["issue"]
    assert found["years"] == [
        {"year": 2024, "count": 1, "listed": 1, "ids": [ledger["transfer"]],
         "income": "0.00", "basis": "0.00", "proceeds": "0.00", "fees": "2.00"},
        {"year": 2025, "count": 3, "listed": 2, "ids": [ledger["income"], ledger["tiny"], ledger["spend"]],
         "income": "1000.10", "basis": "1000.10", "proceeds": "500.00", "fees": "1.00"},
    ]
    assert len(found["explanation"]) == 3 and "filed" in found["explanation"][1]
    assert ledger["typed"] not in [i["id"] for i in found["items"]]
    assert tx(auth_client, ledger["inherited"])["price_moment"] == "day"  # a day value, but not listed


def test_an_inheritance_is_never_moved_to_the_hour(auth_client, ledger, test_engine):
    r = auth_client.post("/api/review/hourly-prices", json={"year": 2025})
    (Path(test_engine.url.database).parent / "backups" / r.json()["backup"]).unlink()
    assert ledger["inherited"] not in [c["id"] for c in r.json()["changed"]]
    assert auth_client.post("/api/review/hourly-prices", json={"ids": [ledger["inherited"]]}).json() == {
        "changed": [], "recalculated": False, "backup": None}
    inherited = tx(auth_client, ledger["inherited"])
    assert (inherited["cost_basis_usd"], inherited["price_moment"]) == ("3000.00", "day")


def test_nothing_changes_until_applied(auth_client, ledger):
    before = tx(auth_client, ledger["income"])
    check(auth_client)
    assert tx(auth_client, ledger["income"]) == before


def test_applying_picked_items_makes_a_backup_and_prices_them_at_the_hour(auth_client, ledger, test_engine):
    r = auth_client.post("/api/review/hourly-prices", json={"ids": [ledger["spend"], ledger["typed"]]})
    assert r.status_code == 200, r.text
    assert [c["id"] for c in r.json()["changed"]] == [ledger["spend"]]  # a typed value never changes
    backup = Path(test_engine.url.database).parent / "backups" / r.json()["backup"]
    assert backup.exists()
    backup.unlink()
    spend = tx(auth_client, ledger["spend"])
    assert (spend["gross_proceeds_usd"], spend["fee_usd"], spend["price_moment"]) == ("2000.00", "4.00", "hour")
    assert D(spend["proceeds_usd"]) == D("1996.00")  # recalculated: the fee comes off the proceeds (#157)
    assert tx(auth_client, ledger["income"])["cost_basis_usd"] == "3000.00"
    assert tx(auth_client, ledger["typed"])["cost_basis_usd"] == "999.00"


def test_applying_a_year_applies_its_small_changes_and_no_other_year(auth_client, ledger, test_engine):
    r = auth_client.post("/api/review/hourly-prices", json={"year": 2025})
    assert r.status_code == 200, r.text
    assert sorted(c["id"] for c in r.json()["changed"]) == sorted([ledger["income"], ledger["tiny"], ledger["spend"]])
    (Path(test_engine.url.database).parent / "backups" / r.json()["backup"]).unlink()
    assert tx(auth_client, ledger["tiny"])["cost_basis_usd"] == "0.40"
    assert tx(auth_client, ledger["transfer"])["fee_usd"] == "6.00"
    found = check(auth_client)
    assert [i["id"] for i in found["items"]] == [ledger["transfer"]]
    assert [y["year"] for y in found["years"]] == [2024]


def test_ids_or_a_year_not_both(auth_client, ledger):
    assert auth_client.post("/api/review/hourly-prices", json={}).status_code == 422
    assert auth_client.post("/api/review/hourly-prices", json={"ids": [1], "year": 2025}).status_code == 422


def test_the_typed_income_check_compares_with_the_hour_and_skips_priced_values(auth_client, ledger):
    review = auth_client.get("/api/review").json()
    off = next(c for c in review["checks"] if c["key"] == "income_value_off")
    assert [i["id"] for i in off["items"]] == [ledger["typed"]]
    assert "at that hour's price ($40000.00) it is $4000.00" in off["items"][0]["issue"]


def test_the_cli_applies_a_year(auth_client, ledger, test_engine, monkeypatch, capsys):
    from sqlalchemy.orm import sessionmaker

    from backend import cli as backend_cli
    from backend import database

    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=test_engine))
    monkeypatch.setattr(database, "init_db", lambda: None)
    assert backend_cli.main(["review", "--apply-hourly-prices", "2024"]) == 0
    out = capsys.readouterr().out
    assert f"#{ledger['transfer']}  fee_usd $6.00 -> $8.00  (at the hour's price)" in out
    assert "Changed 1 transaction(s) and recalculated." in out
    backup = out.split("Backup copy first: backups/")[1].split("\n")[0]
    (Path(test_engine.url.database).parent / "backups" / backup).unlink()
    assert tx(auth_client, ledger["transfer"])["fee_usd"] == "8.00"


def test_an_applys_copy_never_pushes_out_the_pre_upgrade_copies(auth_client, ledger, test_engine):
    """Review of #175: the copies before an apply are their own kind; five
    applies of one item each mustn't prune the upgrade's "before" copies."""
    backups = Path(test_engine.url.database).parent / "backups"
    backups.mkdir(exist_ok=True)
    stem = Path(test_engine.url.database).stem
    before = [backups / f"{stem}-before-schema-0010-20260101T00000{n}Z.db" for n in range(5)]
    for path in before:
        path.write_bytes(b"")
    try:
        r = auth_client.post("/api/review/hourly-prices", json={"ids": [ledger["income"]]})
        assert "-review-hourly-prices-" in r.json()["backup"]
        assert all(path.exists() for path in before)
    finally:
        for path in backups.glob(f"{stem}-*.db"):
            path.unlink()


def test_too_many_or_too_large_ids_are_refused_not_a_server_error(auth_client, ledger):
    """Review of #175: one SQL IN (...) can't take 40,000 ids, nor SQLite an id of 2**70."""
    assert auth_client.post("/api/review/hourly-prices", json={"ids": list(range(1, 10002))}).status_code == 422
    assert auth_client.post("/api/review/hourly-prices", json={"ids": [2**70]}).status_code == 422


def test_the_cli_text_shows_each_year_and_how_to_apply_it(auth_client, ledger):
    """Review of #175: a year with only changes under $1.00 lists no item,
    but the CLI is the only other way to apply it: its line and the action show."""
    from backend.services.review import format_text

    text = format_text(auth_client.get("/api/review").json())
    assert ("  2025: 3 transaction(s), 1 by less than $1.00 each (not listed); totals: income +$1000.10, "
            "basis +$1000.10, proceeds before fees +$500.00, fee values +$1.00") in text
    assert "  2024: 1 transaction(s); totals: fee values +$2.00" in text
    assert "--apply-hourly-prices YEAR" in text
