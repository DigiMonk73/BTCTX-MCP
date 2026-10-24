"""
Property tests: random valid ledgers must keep the tax invariants.

Hypothesis builds a sequence of transactions (deposits, buys, sells,
transfers with BTC fees, spends, gifts, donations, lost coins, income), each
valid at its moment: balances are tracked in satoshis while drawing, so a
sell or withdrawal never exceeds what the account holds. One generator keeps
to 1.x's accounts; a second (2.0) draws among multiple wallets, exchanges
and banks, on a database of its own. The ledger is entered through the API,
then checked:

- each bitcoin account's balance = the model = the BTC left in its lots;
- no lot is negative or above its size;
- every disposal: gain = proceeds - basis (Gift/Donation/Lost: $0 and $0);
- cost basis is conserved: what came in = what's left in lots + what was
  disposed (transfers move basis between lots, they never create or lose it);
- long-term only when sold after the one-year anniversary (tax timezone);
- Form 8949 rows add up to Schedule D, and to the disposals of the year;
- recalculating changes nothing; entering the same ledger in another order
  gives the same result.

The fast set runs a few examples; the slow profile (CI) runs many more.
"""

from __future__ import annotations

import random
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List
from zoneinfo import ZoneInfo

import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services import first_run
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data
from backend.services.transaction import cost_left
from backend.tests.account_pairs import COLD, CREDIT_UNION, KRAKEN_BTC, KRAKEN_USD, add_them
from backend.tests.conftest import default_login, init_test_db, remove_temp_db, temp_db_file

BANK, WALLET, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 2, 3, 4, 99
SAT = Decimal("0.00000001")
CENT = Decimal("0.01")
NON_TAXABLE = {"gift", "donation", "lost"}

# The second generator's accounts: 1.x's and a second bank, wallet and
# exchange, as the account API makes them on a fresh ledger (add_them)
BANKS = (BANK, CREDIT_UNION)
WALLETS = (WALLET, COLD)
EXCHANGES = ((EXCH_USD, EXCH_BTC), (KRAKEN_USD, KRAKEN_BTC))  # each one's USD and BTC
DOLLAR_ACCOUNTS = BANKS + tuple(usd for usd, _btc in EXCHANGES)
BITCOIN_ACCOUNTS = WALLETS + tuple(btc for _usd, btc in EXCHANGES)


def btc(sats: int) -> str:
    return str((Decimal(sats) * SAT).quantize(SAT))


@dataclass
class Model:
    """The BTC each account holds, in satoshis, by account id."""
    held: Dict[int, int] = field(default_factory=dict)

    def get(self, acct: int) -> int:
        return self.held.get(acct, 0)

    def add(self, acct: int, sats: int) -> None:
        self.held[acct] = self.get(acct) + sats


class Clock:
    """Strictly increasing transaction times, drawn."""

    def __init__(self, data):
        self.data = data
        self.t = datetime(2022, 1, 3, 15, 0, tzinfo=timezone.utc)

    def next(self) -> str:
        # Up to 60 days apart: 25 operations stay within the past (future
        # dates are refused), and holding periods still cross one year.
        days = self.data.draw(st.integers(1, 60), label="gap_days")
        minutes = self.data.draw(st.integers(0, 24 * 60 - 1), label="minutes")
        self.t = self.t + timedelta(days=days, minutes=minutes)
        if self.t.month == 2 and self.t.day == 29:  # keep anniversaries unambiguous
            self.t += timedelta(days=1)
        return self.t.strftime("%Y-%m-%dT%H:%M:%SZ")


def draw_ledger(data, max_ops: int) -> tuple[List[dict], Model]:
    """A valid transaction sequence (strictly increasing times) and the BTC model."""
    m = Model()
    when = Clock(data).next
    txs: List[dict] = []

    # Plenty of dollars in both USD accounts.
    for acct in (BANK, EXCH_USD):
        txs.append(dict(type="Deposit", timestamp=when(), from_account_id=EXTERNAL, to_account_id=acct,
                        amount="100000000", fee_amount="0", fee_currency="USD", source="N/A"))

    n = data.draw(st.integers(3, max_ops), label="ops")
    for _ in range(n):
        choices = ["buy", "deposit"]
        if m.get(EXCH_BTC) >= 1000:
            choices.append("sell")
        if max(m.get(WALLET), m.get(EXCH_BTC)) >= 2000:
            choices += ["transfer", "withdraw"]
        op = data.draw(st.sampled_from(choices), label="op")
        ts = when()

        if op == "buy":
            sats = data.draw(st.integers(100_000, 50_000_000), label="buy_sats")
            cost = Decimal(data.draw(st.integers(1_000, 5_000_000), label="buy_cents")) * CENT
            src = data.draw(st.sampled_from([BANK, EXCH_USD]), label="buy_from")
            txs.append(dict(type="Buy", timestamp=ts, from_account_id=src, to_account_id=EXCH_BTC,
                            amount=btc(sats), cost_basis_usd=str(cost), fee_amount="0", fee_currency="USD"))
            m.add(EXCH_BTC, sats)

        elif op == "deposit":
            acct = data.draw(st.sampled_from([WALLET, EXCH_BTC]), label="dep_to")
            sats = data.draw(st.integers(10_000, 20_000_000), label="dep_sats")
            source = data.draw(st.sampled_from(["MyBTC", "Gift", "Income", "Interest"]), label="source")
            d = dict(type="Deposit", timestamp=ts, from_account_id=EXTERNAL, to_account_id=acct,
                     amount=btc(sats), fee_amount="0", fee_currency="BTC", source=source)
            if source in ("MyBTC", "Gift") or data.draw(st.booleans(), label="income_basis_given"):
                d["cost_basis_usd"] = str(Decimal(data.draw(st.integers(0, 2_000_000), label="dep_cents")) * CENT)
            txs.append(d)
            m.add(acct, sats)

        elif op == "sell":
            sats = data.draw(st.integers(1000, m.get(EXCH_BTC)), label="sell_sats")
            gross = Decimal(data.draw(st.integers(100, 10_000_000), label="sell_cents")) * CENT
            fee = min(gross, Decimal(data.draw(st.integers(0, 2000), label="sell_fee_cents")) * CENT)
            txs.append(dict(type="Sell", timestamp=ts, from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
                            amount=btc(sats), gross_proceeds_usd=str(gross), fee_amount=str(fee), fee_currency="USD"))
            m.add(EXCH_BTC, -sats)

        elif op == "transfer":
            src = data.draw(st.sampled_from([a for a in (WALLET, EXCH_BTC) if m.get(a) >= 2000]), label="tr_from")
            dst = EXCH_BTC if src == WALLET else WALLET
            sats = data.draw(st.integers(2000, m.get(src)), label="tr_sats")
            fee = data.draw(st.integers(0, min(sats - 1000, 50_000)), label="tr_fee")
            txs.append(dict(type="Transfer", timestamp=ts, from_account_id=src, to_account_id=dst,
                            amount=btc(sats), fee_amount=btc(fee), fee_currency="BTC"))
            m.add(src, -sats)
            m.add(dst, sats - fee)

        else:  # withdraw
            src = data.draw(st.sampled_from([a for a in (WALLET, EXCH_BTC) if m.get(a) >= 2000]), label="wd_from")
            fee = data.draw(st.integers(0, min(10_000, m.get(src) - 1000)), label="wd_fee")
            sats = data.draw(st.integers(1000, m.get(src) - fee), label="wd_sats")
            purpose = data.draw(st.sampled_from(["Spent", "Gift", "Donation", "Lost"]), label="purpose")
            d = dict(type="Withdrawal", timestamp=ts, from_account_id=src, to_account_id=EXTERNAL,
                     amount=btc(sats), fee_amount=btc(fee), fee_currency="BTC", purpose=purpose)
            if purpose == "Spent" and data.draw(st.booleans(), label="spent_priced"):
                d["proceeds_usd"] = str(Decimal(data.draw(st.integers(0, 5_000_000), label="wd_cents")) * CENT)
            txs.append(d)
            m.add(src, -(sats + fee))
    return txs, m


def draw_multi_ledger(data, max_ops: int) -> tuple[List[dict], Model]:
    """Like draw_ledger, among two banks, two wallets and two exchanges by
    2.0's routes (spec 5.5): a Buy on either exchange, a Sell on the one
    that holds the coins, bitcoin and dollars moved between any two of
    their accounts, a consolidation within one."""
    m = Model()
    when = Clock(data).next
    # Plenty of dollars in every USD account; dollars aren't modelled.
    txs = [dict(type="Deposit", timestamp=when(), from_account_id=EXTERNAL, to_account_id=acct,
                amount="100000000", fee_amount="0", fee_currency="USD", source="N/A") for acct in DOLLAR_ACCOUNTS]

    n = data.draw(st.integers(3, max_ops), label="ops")
    for _ in range(n):
        ops = [_buy_on_either, _deposit_into_any, _move_dollars]
        if any(m.get(btc_acct) >= 1000 for _usd, btc_acct in EXCHANGES):
            ops.append(_sell_on_one)
        if any(m.get(acct) >= 2000 for acct in BITCOIN_ACCOUNTS):
            ops += [_move_bitcoin, _withdraw_from_any]
        op = data.draw(st.sampled_from(ops), label="op")
        txs.append(op(data, m, when()))
    return txs, m


def _buy_on_either(data, m: Model, ts: str) -> dict:
    """Paid from either bank, or from that exchange's own dollars."""
    usd, btc_acct = data.draw(st.sampled_from(EXCHANGES), label="buy_on")
    src = data.draw(st.sampled_from(BANKS + (usd,)), label="buy_from")
    sats = data.draw(st.integers(100_000, 50_000_000), label="buy_sats")
    cost = Decimal(data.draw(st.integers(1_000, 5_000_000), label="buy_cents")) * CENT
    fee = Decimal(data.draw(st.integers(0, 2000), label="buy_fee_cents")) * CENT
    m.add(btc_acct, sats)
    return dict(type="Buy", timestamp=ts, from_account_id=src, to_account_id=btc_acct,
                amount=btc(sats), cost_basis_usd=str(cost), fee_amount=str(fee), fee_currency="USD")


def _deposit_into_any(data, m: Model, ts: str) -> dict:
    acct = data.draw(st.sampled_from(BITCOIN_ACCOUNTS), label="dep_to")
    sats = data.draw(st.integers(10_000, 20_000_000), label="dep_sats")
    source = data.draw(st.sampled_from(["MyBTC", "Gift", "Income", "Interest"]), label="source")
    d = dict(type="Deposit", timestamp=ts, from_account_id=EXTERNAL, to_account_id=acct,
             amount=btc(sats), fee_amount="0", fee_currency="BTC", source=source)
    if source in ("MyBTC", "Gift") or data.draw(st.booleans(), label="income_basis_given"):
        d["cost_basis_usd"] = str(Decimal(data.draw(st.integers(0, 2_000_000), label="dep_cents")) * CENT)
    m.add(acct, sats)
    return d


def _sell_on_one(data, m: Model, ts: str) -> dict:
    """From an exchange's BTC into that same exchange's USD."""
    usd, btc_acct = data.draw(st.sampled_from([e for e in EXCHANGES if m.get(e[1]) >= 1000]), label="sell_on")
    sats = data.draw(st.integers(1000, m.get(btc_acct)), label="sell_sats")
    gross = Decimal(data.draw(st.integers(100, 10_000_000), label="sell_cents")) * CENT
    fee = min(gross, Decimal(data.draw(st.integers(0, 2000), label="sell_fee_cents")) * CENT)
    m.add(btc_acct, -sats)
    return dict(type="Sell", timestamp=ts, from_account_id=btc_acct, to_account_id=usd,
                amount=btc(sats), gross_proceeds_usd=str(gross), fee_amount=str(fee), fee_currency="USD")


def _move_bitcoin(data, m: Model, ts: str) -> dict:
    """Between any two bitcoin accounts (wallet to wallet, a wallet to or
    from either exchange, one exchange to the other), its fee within the
    amount; or within one, a consolidation, which moves no coins and records
    only its network fee, so it needs one (#159)."""
    src = data.draw(st.sampled_from([a for a in BITCOIN_ACCOUNTS if m.get(a) >= 2000]), label="tr_from")
    dst = data.draw(st.sampled_from(BITCOIN_ACCOUNTS), label="tr_to")
    sats = data.draw(st.integers(2000, m.get(src)), label="tr_sats")
    fee = data.draw(st.integers(1 if dst == src else 0, min(sats - 1000, 50_000)), label="tr_fee")
    m.add(src, -sats)
    m.add(dst, sats - fee)
    return dict(type="Transfer", timestamp=ts, from_account_id=src, to_account_id=dst,
                amount=btc(sats), fee_amount=btc(fee), fee_currency="BTC")


def _withdraw_from_any(data, m: Model, ts: str) -> dict:
    src = data.draw(st.sampled_from([a for a in BITCOIN_ACCOUNTS if m.get(a) >= 2000]), label="wd_from")
    fee = data.draw(st.integers(0, min(10_000, m.get(src) - 1000)), label="wd_fee")
    sats = data.draw(st.integers(1000, m.get(src) - fee), label="wd_sats")
    purpose = data.draw(st.sampled_from(["Spent", "Gift", "Donation", "Lost"]), label="purpose")
    d = dict(type="Withdrawal", timestamp=ts, from_account_id=src, to_account_id=EXTERNAL,
             amount=btc(sats), fee_amount=btc(fee), fee_currency="BTC", purpose=purpose)
    if purpose == "Spent" and data.draw(st.booleans(), label="spent_priced"):
        d["proceeds_usd"] = str(Decimal(data.draw(st.integers(0, 5_000_000), label="wd_cents")) * CENT)
    m.add(src, -(sats + fee))
    return d


def _move_dollars(data, m: Model, ts: str) -> dict:
    """Between any two dollar accounts: bank to bank, a bank to or from
    either exchange, one exchange to the other; its fee on top (#477)."""
    src = data.draw(st.sampled_from(DOLLAR_ACCOUNTS), label="usd_from")
    dst = data.draw(st.sampled_from([a for a in DOLLAR_ACCOUNTS if a != src]), label="usd_to")
    amount = Decimal(data.draw(st.integers(1, 100_000_000), label="usd_cents")) * CENT
    fee = Decimal(data.draw(st.integers(0, 2000), label="usd_fee_cents")) * CENT
    return dict(type="Transfer", timestamp=ts, from_account_id=src, to_account_id=dst,
                amount=str(amount), fee_amount=str(fee), fee_currency="USD")


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
class Ledger:
    def __init__(self, client, engine):
        self.client = client
        self.Session = sessionmaker(bind=engine)

    def reset(self) -> None:
        assert self.client.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204

    def enter(self, txs: List[dict]) -> None:
        for tx in txs:
            r = self.client.post("/api/transactions", json=tx)
            assert r.status_code == 200, f"{tx} -> {r.status_code} {r.text}"

    def enter_any_order(self, txs: List[dict], rng: random.Random) -> bool:
        """Enter in a shuffled order; a transaction the ledger can't take yet
        (it would spend BTC entered later) is retried after the others. When
        none of the rest can go in alone (e.g. two transfers that feed each
        other, with an entered sale relying on the round trip), no one could
        enter them in this order: False, and the example is discarded."""
        pending = txs[:]
        rng.shuffle(pending)
        while pending:
            deferred = []
            for tx in pending:
                r = self.client.post("/api/transactions", json=tx)
                if r.status_code != 200:
                    deferred.append(tx)
            if len(deferred) == len(pending):
                return False
            pending = deferred
        return True

    def snapshot(self) -> Dict[str, list]:
        """Results keyed by timestamp (unique per transaction), not by id."""
        with self.Session() as db:
            txs = db.query(Transaction).order_by(Transaction.timestamp).all()
            by_id = {t.id: t.timestamp for t in txs}
            tx_rows = [
                (t.timestamp, t.type, t.amount, t.cost_basis_usd, t.gross_proceeds_usd, t.proceeds_usd,
                 t.realized_gain_usd, t.holding_period)
                for t in txs
            ]
            disposals = sorted(
                (by_id[d.transaction_id], d.lot.acquired_date, d.disposed_btc, d.disposal_basis_usd,
                 d.proceeds_usd_for_that_portion, d.realized_gain_usd, d.holding_period)
                for d in db.query(LotDisposal).all()
            )
            lots = sorted(
                (by_id[lot.created_txn_id], lot.acquired_date, lot.total_btc, lot.remaining_btc, lot.cost_basis_usd)
                for lot in db.query(BitcoinLot).all()
            )
        return {"transactions": tx_rows, "disposals": disposals, "lots": lots}

    def tax_zone(self) -> ZoneInfo:
        return ZoneInfo(self.client.get("/api/settings/tax-timezone").json()["timezone"])

    def bitcoin_accounts(self) -> set[int]:
        """Every wallet and every exchange's BTC account, the account API's
        included (2.0); not BTC Fees."""
        accounts = self.client.get("/api/accounts/").json()
        return {a["id"] for a in accounts if a["currency"] == "BTC" and a["kind"] != "fee"}


def local_date(ts: datetime, tz: ZoneInfo):
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(tz).date()


def check_invariants(ledger: Ledger, txs: List[dict], model: Model) -> None:
    client = ledger.client
    rows = client.get("/api/calculations/accounts/balances").json()
    balances = {b["account_id"]: Decimal(str(b["balance"])) for b in rows}
    bitcoin = ledger.bitcoin_accounts()
    assert {acct: balances[acct] for acct in bitcoin} == {acct: Decimal(model.get(acct)) * SAT for acct in bitcoin}

    tz = ledger.tax_zone()
    with ledger.Session() as db:
        txs_db = {t.id: t for t in db.query(Transaction).all()}
        lots = db.query(BitcoinLot).all()
        disposals = db.query(LotDisposal).all()

        # Lots: a pile per bitcoin account, holding its balance; never
        # negative, never above their size.
        left: Dict[int, Decimal] = dict.fromkeys(bitcoin, Decimal(0))
        for lot in lots:
            assert Decimal(0) <= lot.remaining_btc <= lot.total_btc, (lot.id, lot.remaining_btc, lot.total_btc)
            left[txs_db[lot.created_txn_id].to_account_id] += lot.remaining_btc
        assert left == {acct: balances[acct] for acct in bitcoin}

        # Disposals: gain = proceeds - basis; a gift/donation/lost amount carries
        # nothing, but its network fee is a disposal like any other (F24); a
        # transaction's fee disposals add up to its stored fee value, except a
        # spend's, which is a cost of the spend (#157): the spend and its fee
        # together realize what the spend brought in, the fee at most that.
        fee_parts, amount_parts = defaultdict(Decimal), defaultdict(Decimal)
        for d in disposals:
            tx = txs_db[d.transaction_id]
            if d.is_fee:
                fee_parts[tx.id] += d.proceeds_usd_for_that_portion
                assert d.realized_gain_usd == d.proceeds_usd_for_that_portion - d.disposal_basis_usd, d.id
            elif tx.type == "Withdrawal" and (tx.purpose or "").lower() in NON_TAXABLE:
                assert d.proceeds_usd_for_that_portion == 0 and d.realized_gain_usd == 0, (tx.purpose, d.id)
            else:
                amount_parts[tx.id] += d.proceeds_usd_for_that_portion
                assert d.realized_gain_usd == d.proceeds_usd_for_that_portion - d.disposal_basis_usd, d.id
            # Holding period: long-term only after the one-year anniversary.
            acquired = local_date(d.lot.acquired_date, tz)
            sold = local_date(tx.timestamp, tz)
            anniversary = acquired.replace(year=acquired.year + 1)
            expected = "LONG" if sold > anniversary else "SHORT"
            assert d.holding_period == expected, (acquired, sold, d.holding_period)
        for tx_id, total in fee_parts.items():
            tx = txs_db[tx_id]
            if tx.type == "Withdrawal" and (tx.purpose or "").lower() == "spent":
                assert total == min(tx.fee_usd, tx.gross_proceeds_usd), (tx_id, total, tx.fee_usd)
                assert total + amount_parts[tx_id] == tx.gross_proceeds_usd, (tx_id, tx.gross_proceeds_usd)
            else:
                assert total == tx.fee_usd, (tx_id, total, tx.fee_usd)

        # Basis conservation, to the cent (#100): what was acquired is what
        # the disposals claimed plus what's held, through any sells, spends,
        # fees, transfers and consolidations; no piece claims less than 0.
        acquired_basis = sum(
            (lot.cost_basis_usd for lot in lots if txs_db[lot.created_txn_id].type in ("Buy", "Deposit")),
            Decimal(0),
        )
        remaining_basis = sum((cost_left(lot) for lot in lots), Decimal(0))
        disposed_basis = sum((d.disposal_basis_usd for d in disposals), Decimal(0))
        assert all(d.disposal_basis_usd >= 0 and d.proceeds_usd_for_that_portion >= 0 for d in disposals)  # #297
        assert acquired_basis == remaining_basis + disposed_basis, (acquired_basis, remaining_basis, disposed_basis)

        # Form 8949 = Schedule D = the year's taxable disposals.
        years = sorted({local_date(t.timestamp, tz).year for t in txs_db.values()})
        for year in years:
            forms = build_form_8949_and_schedule_d(year, db)
            for term, rows in (("short_term", forms["short_term"]), ("long_term", forms["long_term"])):
                totals = forms["schedule_d"][term]
                assert sum((Decimal(str(r["proceeds"])) for r in rows), Decimal(0)) == Decimal(str(totals["proceeds"]))
                assert sum((Decimal(str(r["cost"])) for r in rows), Decimal(0)) == Decimal(str(totals["cost"]))
                assert sum((Decimal(str(r["gain_loss"])) for r in rows), Decimal(0)) == Decimal(str(totals["gain_loss"]))
            taxable = [
                d for d in disposals
                if local_date(txs_db[d.transaction_id].timestamp, tz).year == year
                and (d.is_fee or not (txs_db[d.transaction_id].type == "Withdrawal"
                                      and (txs_db[d.transaction_id].purpose or "").lower() in NON_TAXABLE))
            ]
            form_gain = sum(
                (Decimal(str(forms["schedule_d"][t]["gain_loss"])) for t in ("short_term", "long_term")), Decimal(0)
            )
            assert form_gain == sum((d.realized_gain_usd for d in taxable), Decimal(0)), year

            # The complete tax report's summary = Schedule D, term by term.
            summary = generate_report_data(db, year)["capital_gains_summary"]
            for term in ("short_term", "long_term"):
                sched = forms["schedule_d"][term]
                assert Decimal(str(summary[term]["proceeds"])) == Decimal(str(sched["proceeds"])), (year, term)
                assert Decimal(str(summary[term]["basis"])) == Decimal(str(sched["cost"])), (year, term)
                assert Decimal(str(summary[term]["gain"])) == Decimal(str(sched["gain_loss"])), (year, term)


def run_property(ledger: Ledger, data, max_ops: int, shuffle: bool, draw=draw_ledger) -> None:
    txs, model = draw(data, max_ops)
    ledger.reset()
    ledger.enter(txs)
    check_invariants(ledger, txs, model)

    before = ledger.snapshot()
    for _ in range(2):
        assert ledger.client.post("/api/transactions/recalculate").status_code == 200
        assert ledger.snapshot() == before, "recalculating changed the results"

    if shuffle:
        ledger.reset()
        assume(ledger.enter_any_order(txs, random.Random(data.draw(st.integers(0, 2**32 - 1), label="seed"))))
        assert ledger.snapshot() == before, "entry order changed the results"


@pytest.fixture(scope="module")
def ledger(auth_client, test_engine):
    lg = Ledger(auth_client, test_engine)
    yield lg
    lg.reset()


FAST = settings(max_examples=8, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])
SLOW = settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large])


@FAST
@given(data=st.data())
def test_random_ledgers_keep_the_invariants(ledger, data):
    run_property(ledger, data, max_ops=12, shuffle=True)


@pytest.mark.slow
@SLOW
@given(data=st.data())
def test_random_ledgers_keep_the_invariants_many(ledger, data):
    run_property(ledger, data, max_ops=25, shuffle=True)


@pytest.fixture(scope="module")
def own_database(auth_client):
    """
    A database of its own for the multiple-account ledgers, with a second
    bank, wallet and exchange made through the account API (add_them):
    accounts made in the session's shared database would stay there for
    every later test. Yields a Ledger on it, logged in there.
    """
    path = temp_db_file()
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    first_run.clear_code()
    try:
        lg = Ledger(TestClient(app), engine)
        with serving(lg):
            assert lg.client.post("/api/login", json=default_login()).status_code == 200
            add_them(lg.client)
            assert lg.bitcoin_accounts() == set(BITCOIN_ACCOUNTS)
        yield lg
    finally:
        first_run.clear_code()
        engine.dispose()
        remove_temp_db(path)


@pytest.fixture
def multi_ledger(own_database):
    """That ledger, with the app on its database for one test: the app
    takes its database from one override, and the module's other tests run
    on the session's."""
    with serving(own_database):
        yield own_database


@contextmanager
def serving(lg: Ledger):
    """The app on that ledger's database for the block, then back on the one before."""
    def override():
        db = lg.Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override
    try:
        yield
    finally:
        app.dependency_overrides[get_db] = previous


# multi_ledger swaps the app's database once a test, not once an example:
# nothing in it needs resetting between examples (each one resets the ledger)
ONE_SWAP_A_TEST = [*FAST.suppress_health_check, HealthCheck.function_scoped_fixture]


@settings(FAST, suppress_health_check=ONE_SWAP_A_TEST)
@given(data=st.data())
def test_random_ledgers_over_multiple_accounts_keep_the_invariants(multi_ledger, data):
    run_property(multi_ledger, data, max_ops=12, shuffle=True, draw=draw_multi_ledger)


@pytest.mark.slow
@settings(SLOW, suppress_health_check=ONE_SWAP_A_TEST)
@given(data=st.data())
def test_random_ledgers_over_multiple_accounts_keep_the_invariants_many(multi_ledger, data):
    run_property(multi_ledger, data, max_ops=25, shuffle=True, draw=draw_multi_ledger)


def test_an_order_no_one_could_enter_is_discarded_not_failed(ledger):
    """Why the slow property test failed now and then (2026-09-29): two
    transfers that feed each other, with a sale relying on the round trip,
    can only be entered together, and the app rightly refuses each alone.
    Such a shuffled order is thrown away (Hypothesis draws another), not
    reported as "stuck"."""
    ledger.reset()
    ledger.enter([
        dict(type="Deposit", timestamp="2023-01-01T12:00:00Z", from_account_id=99, to_account_id=1,
             amount="50000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2023-01-02T12:00:00Z", from_account_id=1, to_account_id=4,
             amount="1", cost_basis_usd="20000", fee_amount="0", fee_currency="USD"),
        dict(type="Sell", timestamp="2023-01-05T12:00:00Z", from_account_id=4, to_account_id=3,
             amount="1", gross_proceeds_usd="25000", fee_amount="0", fee_currency="USD"),
    ])
    out_and_back = [
        dict(type="Transfer", timestamp="2023-01-03T12:00:00Z", from_account_id=4, to_account_id=2,
             amount="1", fee_amount="0", fee_currency="BTC"),
        dict(type="Transfer", timestamp="2023-01-04T12:00:00Z", from_account_id=2, to_account_id=4,
             amount="1", fee_amount="0", fee_currency="BTC"),
    ]
    assert ledger.enter_any_order(out_and_back, random.Random(0)) is False
    ledger.reset()
