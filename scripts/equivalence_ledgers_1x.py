"""
The equivalence check's own ledgers, frozen at 1.x's (2.0 spec 5.15).

scripts/equivalence_snapshot.py runs on both sides of the check, each side
importing its own backend: a golden ledger or random generator taken from
backend/tests would be the release's on one side and this checkout's on the
other, and 2.0 changes them (multiple wallets, exchanges or accounts). So
the snapshot takes these copies, made verbatim from v1.2.9 (the last 1.x
release): the golden ledger of backend/tests/test_golden_years.py, the
generator of backend/tests/test_invariants_property.py with the snapshot's
seeded draws, and the reference ledger without its "since": "2.0" rows.

Never edited: their value is that they stay 1.x's
(backend/tests/test_equivalence_ledgers_1x.py pins them by digest).
Imports nothing from backend, btctx_mcp or scripts.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import List  # noqa: UP035  (verbatim 1.x code)

from hypothesis import strategies as st

# A reference-ledger row's notes, never sent to the app
NOTES = ("why", "since")


def reference_rows_1x(path: Path) -> list[dict]:
    """The reference ledger as a 1.x release takes it: the rows a 2.0 step
    added ("since") left out, and no row's notes."""
    rows = json.loads(Path(path).read_text())["transactions"]
    return [{k: v for k, v in row.items() if k not in NOTES} for row in rows if "since" not in row]


# backend/tests/test_invariants_property.py at v1.2.9
BANK, WALLET, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 2, 3, 4, 99


SAT = Decimal("0.00000001")


CENT = Decimal("0.01")


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


def draw_ledger(data, max_ops: int) -> tuple[List[dict], Model]:  # noqa: C901, PLR0915, UP006
    """A valid transaction sequence (strictly increasing times) and the BTC model."""
    m = Model()
    t = datetime(2022, 1, 3, 15, 0, tzinfo=timezone.utc)
    txs: List[dict] = []  # noqa: UP006

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


# The golden ledger, backend/tests/test_golden_years.py's LEDGER at v1.2.9
GOLDEN_LEDGER = [
    dict(type="Deposit", timestamp="2023-01-15T17:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
         amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
    dict(type="Buy", timestamp="2023-02-01T17:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="1.0", cost_basis_usd="23000", fee_amount="0", fee_currency="USD"),
    dict(type="Buy", timestamp="2023-03-01T17:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="0.5", cost_basis_usd="12000", fee_amount="0", fee_currency="USD"),
    dict(type="Transfer", timestamp="2023-06-01T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=WALLET,
         amount="0.6", fee_amount="0.0002", fee_currency="BTC"),
    dict(type="Sell", timestamp="2023-09-10T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.5", gross_proceeds_usd="13000", fee_amount="10", fee_currency="USD"),
    dict(type="Withdrawal", timestamp="2023-12-31T23:30:00-05:00", from_account_id=WALLET,
         to_account_id=EXTERNAL, amount="0.01", proceeds_usd="400", fee_amount="0", fee_currency="BTC",
         purpose="Spent"),
    dict(type="Sell", timestamp="2024-02-02T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.3", gross_proceeds_usd="15000", fee_amount="0", fee_currency="USD"),
    dict(type="Sell", timestamp="2024-03-02T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.1", gross_proceeds_usd="6000", fee_amount="0", fee_currency="USD"),
    dict(type="Deposit", timestamp="2024-05-01T16:00:00Z", from_account_id=EXTERNAL, to_account_id=WALLET,
         amount="0.02", fee_amount="0", fee_currency="BTC", source="Income"),
    dict(type="Withdrawal", timestamp="2024-06-01T16:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
         amount="0.1", fee_amount="0", fee_currency="BTC", purpose="Gift", fmv_usd="6700"),
    dict(type="Buy", timestamp="2025-01-10T17:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
         amount="0.2", cost_basis_usd="20000", fee_amount="0", fee_currency="USD"),
    dict(type="Sell", timestamp="2025-04-01T16:00:00Z", from_account_id=EXCH_BTC, to_account_id=EXCH_USD,
         amount="0.05", gross_proceeds_usd="4000", fee_amount="0", fee_currency="USD"),
    dict(type="Withdrawal", timestamp="2025-05-01T16:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
         amount="0.1", proceeds_usd="9000", fee_amount="0", fee_currency="BTC", purpose="Spent"),
    dict(type="Withdrawal", timestamp="2025-06-01T16:00:00Z", from_account_id=WALLET, to_account_id=EXTERNAL,
         amount="0.01", proceeds_usd="1000", fee_amount="0.0001", fee_currency="BTC", purpose="Spent"),
]


# scripts/equivalence_snapshot.py's at v1.2.9
class SeededDraws:
    """Stands in for Hypothesis's `data` in draw_ledger: the same seed gives
    the same ledger. `overrides` replaces the draw for a label."""

    def __init__(self, seed: int, overrides=None):
        self.rng = random.Random(seed)
        self.overrides = overrides or {}

    def draw(self, strategy, label=None):
        if label in self.overrides:
            return self.overrides[label](self.rng)
        inner = getattr(strategy, "wrapped_strategy", strategy)
        if getattr(inner, "elements", None) is not None:
            return self.rng.choice(list(inner.elements))
        if getattr(inner, "start", None) is not None:
            return self.rng.randint(inner.start, inner.end)
        return self.rng.random() < 0.5
