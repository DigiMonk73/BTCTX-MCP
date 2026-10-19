"""
#549 (owner decision 2026-10-18): a withdrawal's own broker_reporting
override places its network fee's disposal on Form 8949 too, in the same
box as the withdrawal's own row, so a user whose 1099-DA lists the fee can
match it. With no override a fee is on no broker form (I/L from 2025, C/F
before), as before. Only the box moves: the fee's value and gain don't.
"""

from decimal import Decimal

import pytest
from sqlalchemy.orm import sessionmaker

from backend.services.reports.form_8949 import build_form_8949_and_schedule_d

BANK, WALLET, EXCH_BTC, EXTERNAL = 1, 2, 4, 99
FEE, SPEND = "0.00010000 BTC", "0.01000000 BTC"
OVERRIDES = (None, "none", "proceeds", "basis")
# (short, long) box for each override, as for the withdrawal's own row
BOXES_UNTIL_2024 = {None: ("C", "F"), "none": ("C", "F"), "proceeds": ("B", "E"), "basis": ("A", "D")}
BOXES_FROM_2025 = {None: ("I", "L"), "none": ("I", "L"), "proceeds": ("H", "K"), "basis": ("G", "J")}


@pytest.fixture(autouse=True)
def clean(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def post(client, **body):
    r = client.post("/api/transactions", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def buy(client, date):
    """1 BTC for $20,000 on the exchange: a fee of 0.0001 BTC costs $2.00."""
    post(client, type="Deposit", timestamp=f"{date}T11:00:00Z", from_account_id=EXTERNAL,
         to_account_id=BANK, amount="20000", fee_amount="0", fee_currency="USD", source="N/A")
    post(client, type="Buy", timestamp=f"{date}T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="1", cost_basis_usd="20000", fee_amount="0", fee_currency="USD")


def withdraw(client, year, override, purpose="Spent"):
    """0.01 BTC withdrawn from the exchange with a 0.0001 BTC fee worth $5.00."""
    values = {"proceeds_usd": "1000"} if purpose == "Spent" else {"fmv_usd": "500"}
    tx = post(client, type="Withdrawal", timestamp=f"{year}-06-01T12:00:00Z", from_account_id=EXCH_BTC,
              to_account_id=EXTERNAL, amount="0.01", fee_amount="0.0001", fee_currency="BTC",
              fee_usd="5.00", purpose=purpose, broker_reporting=override, **values)
    assert tx["broker_reporting"] == override


def rows(test_engine, year):
    """{description: (box, proceeds, cost, gain)} of the year's Form 8949 rows."""
    with sessionmaker(bind=test_engine)() as db:
        forms = build_form_8949_and_schedule_d(year, db)
    found = forms["short_term"] + forms["long_term"]
    assert len({r["description"] for r in found}) == len(found)
    return {r["description"]: (r["box"], r["proceeds"], r["cost"], r["gain_loss"]) for r in found}


@pytest.mark.parametrize("year", [2024, 2025, 2026])
@pytest.mark.parametrize("term", ["short", "long"])
@pytest.mark.parametrize("override", OVERRIDES)
def test_a_withdrawals_fee_goes_in_the_box_its_override_names(auth_client, test_engine, year, term, override):
    buy(auth_client, f"{year}-01-03" if term == "short" else f"{year - 2}-01-03")
    withdraw(auth_client, year, override)
    boxes = BOXES_UNTIL_2024 if year <= 2024 else BOXES_FROM_2025
    box = boxes[override][term == "long"]
    found = rows(test_engine, year)
    assert found[SPEND][0] == box
    assert found[FEE][0] == box  # the fee follows its withdrawal, never a box of its own


@pytest.mark.parametrize("override", OVERRIDES)
def test_the_override_moves_only_the_fees_box(auth_client, test_engine, override):
    buy(auth_client, "2025-01-03")
    withdraw(auth_client, 2025, override)
    found = rows(test_engine, 2025)
    # The fee: $5.00 for coins that cost $2.00. The spend: $1,000 less that
    # fee (#157) for coins that cost $200.00. Whatever the override.
    assert found[FEE][1:] == (Decimal("5.00"), Decimal("2.00"), Decimal("3.00"))
    assert found[SPEND][1:] == (Decimal("995.00"), Decimal("200.00"), Decimal("795.00"))


@pytest.mark.parametrize("override, box", [(None, "I"), ("none", "I"), ("proceeds", "H"), ("basis", "G")])
def test_a_gifts_fee_follows_the_gifts_override(auth_client, test_engine, override, box):
    """A gift has no row of its own; its fee is its only row, placed by its override."""
    buy(auth_client, "2025-01-03")
    withdraw(auth_client, 2025, override, purpose="Gift")
    assert rows(test_engine, 2025) == {FEE: (box, Decimal("5.00"), Decimal("2.00"), Decimal("3.00"))}


def test_a_transfers_fee_stays_on_no_broker_form(auth_client, test_engine):
    """A transfer takes no override, so its fee is where it always was."""
    buy(auth_client, "2025-01-03")
    post(auth_client, type="Transfer", timestamp="2025-06-01T12:00:00Z", from_account_id=EXCH_BTC,
         to_account_id=WALLET, amount="0.5", fee_amount="0.0001", fee_currency="BTC", fee_usd="5.00")
    assert rows(test_engine, 2025) == {FEE: ("I", Decimal("5.00"), Decimal("2.00"), Decimal("3.00"))}
