"""
Property tests: random valid ledgers must keep the tax invariants.

Hypothesis builds a sequence of transactions (deposits, buys, sells,
transfers with BTC fees, spends, gifts, donations, lost coins, income), each
valid at its moment: balances are tracked in satoshis while drawing, so a
sell or withdrawal never exceeds what the account holds. The ledger is
entered through the API, then checked:

- each BTC account's balance = the model = the BTC left in its lots;
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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, List
from zoneinfo import ZoneInfo

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import sessionmaker

from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services.reports.form_8949 import build_form_8949_and_schedule_d
from backend.services.reports.reporting_core import generate_report_data

BANK, WALLET, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 2, 3, 4, 99
SAT = Decimal("0.00000001")
CENT = Decimal("0.01")
NON_TAXABLE = {"gift", "donation", "lost"}


def btc(sats: int) -> str:
    return str((Decimal(sats) * SAT).quantize(SAT))


@dataclass
class Model:
    wallet: int = 0
    exch: int = 0

    def get(self, acct: int) -> int:
        return self.wallet if acct == WALLET else self.exch

    def add(self, acct: int, sats: int) -> None:
        if acct == WALLET:
            self.wallet += sats
        else:
            self.exch += sats


def draw_ledger(data, max_ops: int) -> tuple[List[dict], Model]:
    """A valid transaction sequence (strictly increasing times) and the BTC model."""
    m = Model()
    t = datetime(2022, 1, 3, 15, 0, tzinfo=timezone.utc)
    txs: List[dict] = []

    def when() -> str:
        nonlocal t
        # Up to 60 days apart: 25 operations stay within the past (future
        # dates are refused), and holding periods still cross one year.
        days = data.draw(st.integers(1, 60), label="gap_days")
        minutes = data.draw(st.integers(0, 24 * 60 - 1), label="minutes")
        t = t + timedelta(days=days, minutes=minutes)
        if t.month == 2 and t.day == 29:  # keep anniversaries unambiguous
            t += timedelta(days=1)
        return t.strftime("%Y-%m-%dT%H:%M:%SZ")

    # Plenty of dollars in both USD accounts.
    for acct in (BANK, EXCH_USD):
        txs.append(dict(type="Deposit", timestamp=when(), from_account_id=EXTERNAL, to_account_id=acct,
                        amount="100000000", fee_amount="0", fee_currency="USD", source="N/A"))

    n = data.draw(st.integers(3, max_ops), label="ops")
    for _ in range(n):
        choices = ["buy", "deposit"]
        if m.exch >= 1000:
            choices.append("sell")
        if max(m.wallet, m.exch) >= 2000:
            choices += ["transfer", "withdraw"]
        op = data.draw(st.sampled_from(choices), label="op")
        ts = when()

        if op == "buy":
            sats = data.draw(st.integers(100_000, 50_000_000), label="buy_sats")
            cost = Decimal(data.draw(st.integers(1_000, 5_000_000), label="buy_cents")) * CENT
            src = data.draw(st.sampled_from([BANK, EXCH_USD]), label="buy_from")
            txs.append(dict(type="Buy", timestamp=ts, from_account_id=src, to_account_id=EXCH_BTC,
                            amount=btc(sats), cost_basis_usd=str(cost), fee_amount="0", fee_currency="USD"))
            m.exch += sats

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
            sats = data.draw(st.integers(1000, m.exch), label="sell_sats")
            gross = Decimal(data.draw(st.integers(100, 10_000_000), label="sell_cents")) * CENT
            fee = min(gross, Decimal(data.draw(st.integers(0, 2000), label="sell_fee_cents")) * CENT)
            txs.append(dict(type="Sell", timestamp=ts, from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
                            amount=btc(sats), gross_proceeds_usd=str(gross), fee_amount=str(fee), fee_currency="USD"))
            m.exch -= sats

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


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
class Ledger:
    def __init__(self, client, engine):
        self.client = client
        self.Session = sessionmaker(bind=engine)

    def reset(self) -> None:
        assert self.client.delete("/api/transactions/delete_all").status_code == 204

    def enter(self, txs: List[dict]) -> None:
        for tx in txs:
            r = self.client.post("/api/transactions", json=tx)
            assert r.status_code == 200, f"{tx} -> {r.status_code} {r.text}"

    def enter_any_order(self, txs: List[dict], rng: random.Random) -> None:
        """Enter in a shuffled order; a transaction the ledger can't take yet
        (it would spend BTC entered later) is retried after the others."""
        pending = txs[:]
        rng.shuffle(pending)
        while pending:
            deferred = []
            for tx in pending:
                r = self.client.post("/api/transactions", json=tx)
                if r.status_code != 200:
                    deferred.append(tx)
            assert len(deferred) < len(pending), f"stuck: {deferred[0]}"
            pending = deferred

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


def local_date(ts: datetime, tz: ZoneInfo):
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(tz).date()


def check_invariants(ledger: Ledger, txs: List[dict], model: Model) -> None:
    client = ledger.client
    balances = {b["name"]: Decimal(str(b["balance"])) for b in client.get("/api/calculations/accounts/balances").json()}
    assert balances["Wallet"] == Decimal(model.wallet) * SAT
    assert balances["Exchange BTC"] == Decimal(model.exch) * SAT

    tz = ledger.tax_zone()
    n_ops = len(txs)
    with ledger.Session() as db:
        txs_db = {t.id: t for t in db.query(Transaction).all()}
        lots = db.query(BitcoinLot).all()
        disposals = db.query(LotDisposal).all()

        # Lots: per account, never negative, never above their size.
        left: Dict[int, Decimal] = {WALLET: Decimal(0), EXCH_BTC: Decimal(0)}
        for lot in lots:
            assert Decimal(0) <= lot.remaining_btc <= lot.total_btc, (lot.id, lot.remaining_btc, lot.total_btc)
            left[txs_db[lot.created_txn_id].to_account_id] += lot.remaining_btc
        assert left[WALLET] == balances["Wallet"]
        assert left[EXCH_BTC] == balances["Exchange BTC"]

        # Disposals: gain = proceeds - basis; non-taxable purposes carry nothing.
        for d in disposals:
            tx = txs_db[d.transaction_id]
            if tx.type == "Withdrawal" and (tx.purpose or "").lower() in NON_TAXABLE:
                assert d.proceeds_usd_for_that_portion == 0 and d.realized_gain_usd == 0, (tx.purpose, d.id)
            else:
                assert d.realized_gain_usd == d.proceeds_usd_for_that_portion - d.disposal_basis_usd, d.id
            # Holding period: long-term only after the one-year anniversary.
            acquired = local_date(d.lot.acquired_date, tz)
            sold = local_date(tx.timestamp, tz)
            anniversary = acquired.replace(year=acquired.year + 1)
            expected = "LONG" if sold > anniversary else "SHORT"
            assert d.holding_period == expected, (acquired, sold, d.holding_period)

        # Basis conservation (rounding: at most a cent per operation).
        acquired_basis = sum(
            (lot.cost_basis_usd for lot in lots if txs_db[lot.created_txn_id].type in ("Buy", "Deposit")),
            Decimal(0),
        )
        remaining_basis = sum(
            (lot.cost_basis_usd * lot.remaining_btc / lot.total_btc for lot in lots if lot.total_btc),
            Decimal(0),
        )
        disposed_basis = sum((d.disposal_basis_usd for d in disposals), Decimal(0))
        assert abs(acquired_basis - remaining_basis - disposed_basis) <= CENT * n_ops, (
            acquired_basis, remaining_basis, disposed_basis)

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
                and not (txs_db[d.transaction_id].type == "Withdrawal"
                         and (txs_db[d.transaction_id].purpose or "").lower() in NON_TAXABLE)
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


def run_property(ledger: Ledger, data, max_ops: int, shuffle: bool) -> None:
    txs, model = draw_ledger(data, max_ops)
    ledger.reset()
    ledger.enter(txs)
    check_invariants(ledger, txs, model)

    before = ledger.snapshot()
    for _ in range(2):
        assert ledger.client.post("/api/transactions/recalculate").status_code == 200
        assert ledger.snapshot() == before, "recalculating changed the results"

    if shuffle:
        ledger.reset()
        ledger.enter_any_order(txs, random.Random(data.draw(st.integers(0, 2**32 - 1), label="seed")))
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
