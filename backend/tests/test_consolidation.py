"""
backend/tests/test_consolidation.py

A Transfer from a BTC account to itself (#159): a UTXO consolidation, or a
move between two wallets (or exchanges) BitcoinTX pools as one. Only its
network fee is recorded, as a disposal of the oldest coins at the fee's
value, never broker-reported (IRS digital-asset FAQ Q81, Q97). The coins
that moved keep their lots, dates and basis. Before #159 it was refused.
"""

import io
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.transaction import SAME_ACCOUNT_NEEDS_FEE
from backend.tests.conftest import stub_daily_prices

CLIENT = None
ENGINE = None
BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, BTC_FEES, EXTERNAL = 1, 2, 3, 4, 5, 99


@pytest.fixture(autouse=True, scope="module")
def _setup(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: 100000.0)


@pytest.fixture(autouse=True)
def _clean():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


def tx(**data) -> dict:
    r = CLIENT.post("/api/transactions", json=data)
    assert r.status_code == 200, r.text
    return r.json()


def deposit(day, amount, basis, account=WALLET) -> dict:
    return tx(type="Deposit", timestamp=f"{day}T12:00:00Z", from_account_id=EXTERNAL, to_account_id=account,
              amount=amount, cost_basis_usd=basis, source="MyBTC")


def consolidate(day, amount, fee, account=WALLET, **extra):
    """The response: a Transfer from `account` to itself."""
    return CLIENT.post("/api/transactions", json=dict(
        type="Transfer", timestamp=f"{day}T12:00:00Z", from_account_id=account, to_account_id=account,
        amount=amount, fee_amount=fee, fee_currency="BTC", **extra))


def session():
    return sessionmaker(bind=ENGINE)()


def lots(account) -> list[tuple]:
    """(lot's own transaction, date acquired, BTC, BTC left, basis) of each of the account's lots."""
    db = session()
    try:
        rows = (db.query(BitcoinLot).join(Transaction, Transaction.id == BitcoinLot.created_txn_id)
                .filter(Transaction.to_account_id == account).order_by(BitcoinLot.acquired_date).all())
        return [(lot.created_txn_id, lot.acquired_date.date(), Decimal(lot.total_btc), Decimal(lot.remaining_btc),
                 Decimal(lot.cost_basis_usd)) for lot in rows]
    finally:
        db.close()


def disposals(tx_id) -> list[tuple]:
    """(lot's own transaction, BTC, basis, proceeds, gain, fee?, term) of each of the transaction's disposals."""
    db = session()
    try:
        rows = db.query(LotDisposal).filter(LotDisposal.transaction_id == tx_id).order_by(LotDisposal.id).all()
        return [(d.lot.created_txn_id, Decimal(d.disposed_btc), Decimal(d.disposal_basis_usd),
                 Decimal(d.proceeds_usd_for_that_portion), Decimal(d.realized_gain_usd), d.is_fee, d.holding_period)
                for d in rows]
    finally:
        db.close()


def balances() -> dict:
    rows = CLIENT.get("/api/calculations/accounts/balances").json()
    return {b["account_id"]: Decimal(str(b["balance"])) for b in rows}


def form_8949(year) -> dict:
    db = session()
    try:
        return build_form_8949_and_schedule_d(year, db)
    finally:
        db.close()


def test_a_consolidation_records_only_its_fee():
    old = deposit("2023-03-01", "0.5", "10000.00")
    new = deposit("2025-02-01", "0.3", "27000.00")
    before = lots(WALLET)

    r = consolidate("2025-06-01", "0.8", "0.0001", fee_usd="9.50")
    assert r.status_code == 200, r.text

    # The fee is a disposal of the oldest coins at its value: 0.0001 of a lot
    # that cost $20,000 a BTC, so $2.00 of basis
    assert disposals(r.json()["id"]) == [
        (old["id"], Decimal("0.0001"), Decimal("2.00"), Decimal("9.50"), Decimal("7.50"), True, "LONG")]
    # Nothing else moved: the same two lots, dates and basis, the fee's BTC gone
    after = lots(WALLET)
    assert [lot[:3] + lot[4:] for lot in after] == [lot[:3] + lot[4:] for lot in before]
    assert [lot[3] for lot in after] == [Decimal("0.4999"), Decimal("0.3")]
    assert {lot[0] for lot in after} == {old["id"], new["id"]}
    b = balances()
    assert b[WALLET] == Decimal("0.7999") and b[BTC_FEES] == Decimal("0.0001")


@pytest.mark.parametrize("acquired, moved, year, box", [
    ("2023-03-01", "2025-06-01", 2025, "L"),  # long-term, no 1099-DA
    ("2025-01-10", "2025-06-01", 2025, "I"),  # short-term, no 1099-DA
    ("2023-03-01", "2024-06-01", 2024, "F"),  # before 2025: not on a 1099-B
    ("2024-01-10", "2024-06-01", 2024, "C"),
])
def test_the_fee_is_on_form_8949_never_broker_reported(acquired, moved, year, box):
    deposit(acquired, "0.5", "10000.00")
    assert consolidate(moved, "0.5", "0.0001", fee_usd="6.00").status_code == 200

    forms = form_8949(year)
    rows = forms["short_term"] + forms["long_term"]
    assert [(r["box"], r["description"], r["proceeds"], r["cost"]) for r in rows] == [
        (box, "0.00010000 BTC", Decimal("6.00"), Decimal("2.00"))]


def test_the_fee_takes_the_oldest_coins_first_across_lots():
    first = deposit("2023-01-01", "0.00006", "1.20")
    second = deposit("2024-01-01", "1.0", "40000.00")
    r = consolidate("2025-06-01", "1.00006", "0.0001", fee_usd="10.00")
    assert r.status_code == 200, r.text

    assert disposals(r.json()["id"]) == [
        (first["id"], Decimal("0.00006"), Decimal("1.20"), Decimal("6.00"), Decimal("4.80"), True, "LONG"),
        (second["id"], Decimal("0.00004"), Decimal("1.60"), Decimal("4.00"), Decimal("2.40"), True, "LONG")]
    assert [lot[3] for lot in lots(WALLET)] == [Decimal("0"), Decimal("0.99996")]


def test_a_move_between_pooled_exchanges_leaves_the_lots_as_they_were():
    """Two exchanges pooled as Exchange BTC: only the fee leaves, so the
    coins keep the lot they were bought in, and a later sale's box is worked
    out as before (G for coins bought there in 2026). BitcoinTX can't tell
    which exchange sells: a sale at the other one, whose 1099-DA shows no
    basis, sets its Broker form (the hint and the guide say so)."""
    tx(type="Deposit", timestamp="2026-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=EXCHANGE_USD,
       amount="50000.00", source="N/A")
    tx(type="Buy", timestamp="2026-01-10T12:00:00Z", from_account_id=EXCHANGE_USD, to_account_id=EXCHANGE_BTC,
       amount="1.0", cost_basis_usd="40000.00")
    assert consolidate("2026-02-01", "1.0", "0.0001", account=EXCHANGE_BTC, fee_usd="9.00").status_code == 200
    tx(type="Sell", timestamp="2026-03-01T12:00:00Z", from_account_id=EXCHANGE_BTC, to_account_id=EXCHANGE_USD,
       amount="0.5", gross_proceeds_usd="45000.00")

    rows = form_8949(2026)["short_term"]
    assert [(r["box"], r["description"]) for r in rows] == [("I", "0.00010000 BTC"), ("G", "0.50000000 BTC")]


def test_a_blank_fee_value_is_that_days_price_and_a_typed_one_is_kept():
    deposit("2023-03-01", "1.0", "20000.00")
    priced = consolidate("2025-06-01", "0.5", "0.0001").json()
    typed = consolidate("2025-06-02", "0.5", "0.0001", fee_usd="7.77").json()

    assert (priced["fee_usd"], priced["fee_usd_manual"]) == ("10.00", False)  # 0.0001 x $100,000
    assert (typed["fee_usd"], typed["fee_usd_manual"]) == ("7.77", True)


@pytest.mark.parametrize("account, amount, fee, message", [
    (WALLET, "0.5", "0", SAME_ACCOUNT_NEEDS_FEE),
    (WALLET, "0.5", None, SAME_ACCOUNT_NEEDS_FEE),
    (WALLET, "2.0", "0.0001", "Not enough BTC to transfer"),
    (BANK, "100.00", "0", "Transfer => from and to must be different accounts."),
    (EXCHANGE_USD, "100.00", "1.00", "Transfer => from and to must be different accounts."),
])
def test_what_is_refused(account, amount, fee, message):
    deposit("2023-03-01", "1.0", "20000.00")
    tx(type="Deposit", timestamp="2023-03-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
       amount="500.00", source="N/A")
    tx(type="Deposit", timestamp="2023-03-01T12:00:00Z", from_account_id=EXTERNAL, to_account_id=EXCHANGE_USD,
       amount="500.00", source="N/A")
    r = CLIENT.post("/api/transactions", json=dict(
        type="Transfer", timestamp="2025-06-01T12:00:00Z", from_account_id=account, to_account_id=account,
        amount=amount, fee_amount=fee))
    assert r.status_code == 400, r.text
    assert message in r.json()["detail"]
    assert len(CLIENT.get("/api/transactions").json()) == 3


def test_a_past_consolidation_can_be_added_after_later_moves():
    """Checked against the wallet on its date, not today's: a sweep of the
    whole wallet in June, added after a July gift, was refused (review of #168)."""
    deposit("2023-03-01", "1.0", "20000.00")
    tx(type="Withdrawal", timestamp="2025-07-01T12:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
       amount="0.5", purpose="Gift", fmv_usd="50000.00")
    r = consolidate("2025-06-01", "1.0", "0.0001", fee_usd="10.00")
    assert r.status_code == 200, r.text
    assert balances()[WALLET] == Decimal("0.4999")
    assert [d[1] for d in disposals(r.json()["id"])] == [Decimal("0.0001")]


def test_the_ai_import_takes_a_past_consolidation_too():
    deposit("2023-03-01", "1.0", "20000.00")
    tx(type="Withdrawal", timestamp="2025-07-01T12:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
       amount="0.5", purpose="Gift", fmv_usd="50000.00")
    preview = CLIENT.post("/api/import/entries/preview", json={"rows": [{
        "date": "2025-06-01T12:00:00Z", "type": "Transfer", "amount": "1.0", "from_account": "Wallet",
        "to_account": "Wallet", "fee_amount": "0.0001", "fee_currency": "BTC"}]}).json()
    assert preview["results"][0]["status"] == "ready", preview


def test_a_past_consolidation_of_more_than_the_wallet_held_then_is_refused():
    deposit("2023-03-01", "1.0", "20000.00")
    deposit("2025-08-01", "1.0", "60000.00")  # today's 2.0 would cover it; June's 1.0 doesn't
    r = consolidate("2025-06-01", "1.5", "0.0001")
    assert r.status_code == 400 and "Not enough BTC to transfer" in r.json()["detail"], r.text
    assert len(CLIENT.get("/api/transactions").json()) == 2


def test_a_past_entry_refused_says_a_later_one_may_be_short():
    """Checked in date order, the entry that runs short may be a later one:
    the message says so, so it doesn't read as being about the new entry."""
    deposit("2023-03-01", "1.0", "20000.00")
    tx(type="Transfer", timestamp="2025-06-01T12:00:00Z", from_account_id=WALLET, to_account_id=EXCHANGE_BTC,
       amount="0.5", fee_amount="0.0001", fee_currency="BTC", fee_usd="10.00")
    r = CLIENT.post("/api/transactions", json=dict(
        type="Withdrawal", timestamp="2024-03-01T12:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
        amount="0.8", purpose="Gift", fmv_usd="40000.00"))
    assert r.status_code == 400, r.text
    assert r.json()["detail"].startswith("Not saved: with it, the account would lack BTC on its date or later. "
                                         "Not enough BTC to transfer"), r.text
    assert len(CLIENT.get("/api/transactions").json()) == 2


def test_edits_keep_it_to_the_fee():
    old = deposit("2023-03-01", "1.0", "20000.00")
    move = tx(type="Transfer", timestamp="2025-06-01T12:00:00Z", from_account_id=WALLET,
              to_account_id=EXCHANGE_BTC, amount="0.5", fee_amount="0.0001", fee_currency="BTC")

    # The same move made a consolidation: nothing reaches the exchange
    r = CLIENT.put(f"/api/transactions/{move['id']}", json={"to_account_id": WALLET})
    assert r.status_code == 200, r.text
    assert lots(EXCHANGE_BTC) == []
    assert disposals(move["id"]) == [
        (old["id"], Decimal("0.0001"), Decimal("2.00"), Decimal("10.00"), Decimal("8.00"), True, "LONG")]

    # A new fee is priced again; no fee is refused and changes nothing
    r = CLIENT.put(f"/api/transactions/{move['id']}", json={"fee_amount": "0.0002"})
    assert r.status_code == 200 and r.json()["fee_usd"] == "20.00", r.text
    r = CLIENT.put(f"/api/transactions/{move['id']}", json={"fee_amount": "0"})
    assert r.status_code == 400 and SAME_ACCOUNT_NEEDS_FEE in r.json()["detail"], r.text
    assert balances()[WALLET] == Decimal("0.9998")

    # Deleted, the coins are whole again
    assert CLIENT.delete(f"/api/transactions/{move['id']}").status_code in (200, 204)
    assert [lot[3] for lot in lots(WALLET)] == [Decimal("1.0")]


def test_a_transfer_without_a_fee_cant_become_a_consolidation():
    deposit("2023-03-01", "1.0", "20000.00")
    move = tx(type="Transfer", timestamp="2025-06-01T12:00:00Z", from_account_id=WALLET,
              to_account_id=EXCHANGE_BTC, amount="0.5", fee_amount="0", fee_currency="BTC")
    r = CLIENT.put(f"/api/transactions/{move['id']}", json={"to_account_id": WALLET})
    assert r.status_code == 400 and SAME_ACCOUNT_NEEDS_FEE in r.json()["detail"], r.text
    assert balances()[EXCHANGE_BTC] == Decimal("0.5")


def test_a_full_recalculation_gives_the_same_figures():
    deposit("2023-03-01", "0.00005", "1.00")
    deposit("2024-03-01", "1.0", "60000.00")
    move = consolidate("2025-06-01", "1.00005", "0.0001", fee_usd="11.11").json()
    before = disposals(move["id"])

    assert CLIENT.post("/api/transactions/recalculate").status_code == 200
    assert disposals(move["id"]) == before
    assert sum(d[3] for d in before) == Decimal("11.11")


def test_a_csv_round_trip_keeps_it():
    deposit("2023-03-01", "1.0", "20000.00")
    move = consolidate("2025-06-01", "0.9", "0.0001", fee_usd="9.50").json()
    before = disposals(move["id"])
    exported = CLIENT.get("/api/backup/csv").text
    assert "Wallet,Wallet" in exported

    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    r = CLIENT.post("/api/import/execute", files={"file": ("ledger.csv", io.BytesIO(exported.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    moved = next(t for t in CLIENT.get("/api/transactions").json() if t["type"] == "Transfer")
    assert (moved["from_account_id"], moved["to_account_id"]) == (WALLET, WALLET)
    assert [d[1:] for d in disposals(moved["id"])] == [d[1:] for d in before]


@pytest.mark.parametrize("row, column, message", [
    ("2025-06-01T12:00:00Z,Transfer,0.5,Wallet,Wallet,,,,BTC,,,", "fee_amount", SAME_ACCOUNT_NEEDS_FEE),
    ("2025-06-01T12:00:00Z,Transfer,100,Bank,Bank,,,,USD,,,", "to_account",
     "Transfer must have different from_account and to_account."),
])
def test_a_csv_row_is_checked_like_the_form(row, column, message):
    header = "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency," \
             "source,purpose,notes"
    preview = CLIENT.post("/api/import/preview", files={
        "file": ("ledger.csv", io.BytesIO(f"{header}\n{row}\n".encode()), "text/csv")}).json()
    assert [(e["column"], e["message"]) for e in preview["errors"]] == [(column, message)]


def test_the_ai_import_takes_it():
    deposit("2023-03-01", "1.0", "20000.00")
    row = {"date": "2025-06-01T12:00:00Z", "type": "Transfer", "amount": "0.5", "from_account": "Wallet",
           "to_account": "Wallet", "fee_amount": "0.0001", "fee_currency": "BTC"}
    preview = CLIENT.post("/api/import/entries/preview", json={"rows": [row]}).json()
    assert preview["results"][0]["status"] == "ready", preview
    balances_after = {b["account"]: Decimal(b["balance"]) for b in preview["balances_after"]}
    assert balances_after["Wallet"] == Decimal("0.9999")

    no_fee = dict(row, fee_amount=None)
    result = CLIENT.post("/api/import/entries/preview", json={"rows": [no_fee]}).json()["results"][0]
    assert result["status"] == "invalid" and SAME_ACCOUNT_NEEDS_FEE in result["errors"]


def test_ledger_review_checks_its_fee_value():
    deposit("2023-03-01", "1.0", "20000.00")
    move = consolidate("2025-06-01", "0.5", "0.0001").json()
    with ENGINE.begin() as con:  # valued at another price, as an older version could
        con.execute(text("UPDATE transactions SET fee_usd = '12.00' WHERE id = :id"), {"id": move["id"]})
    review = CLIENT.get("/api/review").json()
    check = next(c for c in review["checks"] if c["key"] == "day_priced_values")
    assert [i["id"] for i in check["items"]] == [move["id"]]
    assert "Fee value $12.00 -> $10.00" in check["items"][0]["change"]
    assert date.fromisoformat(check["items"][0]["date"][:10]) == date(2025, 6, 1)
