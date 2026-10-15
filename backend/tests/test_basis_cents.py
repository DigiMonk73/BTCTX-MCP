"""
Shares to the cent. A lot's cost is claimed to the cent (#100): however a
lot is taken apart, by sells, spends, network fees or transfers, its
pieces' cost basis adds up to what the lot cost, and what's still held
carries the rest. A disposal's proceeds are shared among its lots the same
way (#297): its rows add up to them, and none is below zero.
"""

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import func
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import BitcoinLot, LotDisposal
from backend.services.transaction import cost_left, piece_cost, running_share
from backend.tests.conftest import stub_prices_at

CLIENT: TestClient = None
ENGINE = None

BANK, WALLET, EXCHANGE_USD, EXCHANGE_BTC, EXTERNAL = 1, 2, 3, 4, 99


@pytest.fixture(autouse=True, scope="session")
def _set_client(auth_client, test_engine):
    global CLIENT, ENGINE
    CLIENT, ENGINE = auth_client, test_engine


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_prices_at(monkeypatch, lambda when: Decimal("100000"))


@pytest.fixture(autouse=True)
def _clean_ledger():
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    CLIENT.delete("/api/transactions/delete_all?confirm=DELETE")


def post(**tx):
    r = CLIENT.post("/api/transactions", json=tx)
    assert r.status_code == 200, r.text
    return r.json()


def buy(amount, cost, day=1):
    return post(type="Buy", timestamp=f"2024-01-{day:02d}T12:00:00Z", from_account_id=BANK,
                to_account_id=EXCHANGE_BTC, amount=amount, cost_basis_usd=cost)


def sell(amount, proceeds, day):
    return post(type="Sell", timestamp=f"2024-02-{day:02d}T12:00:00Z", from_account_id=EXCHANGE_BTC,
                to_account_id=EXCHANGE_USD, amount=amount, gross_proceeds_usd=proceeds)


def basis_claimed() -> Decimal:
    with sessionmaker(bind=ENGINE)() as db:
        return db.query(func.sum(LotDisposal.disposal_basis_usd)).scalar() or Decimal(0)


def test_a_lot_sold_in_pieces_claims_its_whole_cost():
    """The issue's example: three 5-satoshi sells claim $0.005 each, which
    rounded alone is $0.00, and the rest $99.985, which rounded alone is
    $99.98: $99.98 of a $100.00 lot."""
    buy("0.001", "100.00")
    for day in (1, 2, 3):
        sell("0.00000005", "0.01", day)
    sell("0.00099985", "100.00", 4)
    assert basis_claimed() == Decimal("100.00")


def test_a_lot_moved_in_pieces_then_sold_claims_its_whole_cost():
    """A transfer moves part of a lot's cost to a new lot, and its network
    fee disposes of a piece: the moved cost, the fee's basis and what's
    sold later still add up to the lot's cost."""
    buy("0.001", "100.00")
    for day in (1, 2, 3):
        post(type="Transfer", timestamp=f"2024-02-{day:02d}T12:00:00Z", from_account_id=EXCHANGE_BTC,
             to_account_id=WALLET, amount="0.00010005", fee_amount="0.00000005", fee_currency="BTC")
    post(type="Withdrawal", timestamp="2024-03-01T12:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
         amount="0.0003", purpose="Spent", gross_proceeds_usd="30.00")
    sell("0.00069985", "70.00", 20)
    assert basis_claimed() == Decimal("100.00")


def disposals() -> list[tuple[Decimal, Decimal]]:
    """(basis, proceeds) of each disposal, in the order made."""
    with sessionmaker(bind=ENGINE)() as db:
        rows = db.query(LotDisposal).order_by(LotDisposal.id).all()
        return [(r.disposal_basis_usd, r.proceeds_usd_for_that_portion) for r in rows]


def test_a_half_cent_of_cost_goes_to_the_piece_that_takes_it():
    """Half of a $1.01 lot is $0.505: an exact half cent rounds up, as the
    IRS rounds (#100), and what's left carries the rest."""
    buy("0.002", "1.01")
    sell("0.001", "1.00", 1)
    assert disposals() == [(Decimal("0.51"), Decimal("1.00"))]
    sell("0.001", "1.00", 2)
    assert basis_claimed() == Decimal("1.01")


def test_a_half_cent_of_proceeds_rounds_up_and_the_shares_add_up():
    """A sell from two lots shares $1.01 of proceeds: $0.505 each, the first
    rounded up, the second the rest of the running total; together, all of
    it."""
    buy("0.001", "50.00", day=1)
    buy("0.001", "50.00", day=2)
    sell("0.002", "1.01", 1)
    assert [proceeds for _, proceeds in disposals()] == [Decimal("0.51"), Decimal("0.50")]


def test_an_exact_half_cent_of_proceeds_is_kept_exact_until_rounded():
    """$27,999.93 shared 5:9: the first lot's share is exactly $9,999.975.
    Divided before multiplied, it came out a hair under the half cent at 28
    digits and went down; it goes up (the review of #295)."""
    buy("0.05", "1000.00", day=1)
    buy("0.09", "1000.00", day=2)
    sell("0.14", "27999.93", 1)
    assert [proceeds for _, proceeds in disposals()] == [Decimal("9999.98"), Decimal("17999.95")]


@settings(max_examples=200, deadline=None)
@given(
    sats=st.integers(min_value=1, max_value=10**10),
    cents=st.integers(min_value=0, max_value=10**9),
    cuts=st.lists(st.integers(min_value=1, max_value=10**10), max_size=12),
)
def test_a_lots_pieces_add_up_to_its_cost(sats, cents, cuts):
    """However a lot is cut, by however many pieces of whatever size, each
    piece costs zero or more, and the pieces and what's left add up to the
    lot's cost to the cent."""
    total = Decimal(sats) / 10**8
    lot = BitcoinLot(total_btc=total, remaining_btc=total, cost_basis_usd=Decimal(cents) / 100)
    claimed = Decimal(0)
    for cut in cuts + [sats]:  # the last piece takes what's left
        qty = min(Decimal(cut) / 10**8, lot.remaining_btc)
        if qty == 0:
            break
        piece = piece_cost(lot, qty)
        assert piece >= 0
        claimed += piece
        lot.remaining_btc -= qty
        assert claimed + cost_left(lot) == lot.cost_basis_usd
    assert lot.remaining_btc == 0 and claimed == lot.cost_basis_usd


def test_a_sale_from_tiny_lots_shares_its_proceeds_without_a_negative_row():
    """#297: six 1-satoshi lots sold together for $0.03. Each lot's share is
    half a cent; rounded on its own, five came to $0.01 and the last, taking
    what's left, to -$0.02. As a running total no row is negative, and the
    rows still add up to the proceeds."""
    for day in range(1, 7):
        buy("0.00000001", "0.01", day=day)
    sell("0.00000006", "0.03", 1)
    shares = [proceeds for _, proceeds in disposals()]
    assert all(share >= 0 for share in shares), shares
    assert sum(shares) == Decimal("0.03")


@settings(max_examples=200, deadline=None)
@given(
    cents=st.integers(min_value=0, max_value=10**9),
    parts=st.lists(st.integers(min_value=1, max_value=10**10), min_size=1, max_size=12),
)
def test_running_shares_add_up_and_none_is_negative(cents, parts):
    """However a value is shared among parts of whatever sizes, each share
    is zero or more and the shares add up to the value to the cent (#297)."""
    value, whole = Decimal(cents) / 100, Decimal(sum(parts)) / 10**8
    before, shares = Decimal(0), []
    for part in parts:
        qty = Decimal(part) / 10**8
        shares.append(running_share(value, before, qty, whole))
        before += qty
    assert all(share >= 0 for share in shares)
    assert sum(shares) == value
