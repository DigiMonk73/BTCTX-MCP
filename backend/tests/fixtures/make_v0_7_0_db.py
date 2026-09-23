"""
Rebuild backend/tests/fixtures/v0_7_0.db: a small real ledger written by the
actual v0.7.0 code (the last release before schema migrations).

    mkdir /tmp/v070 && git archive v0.7.0 backend | tar -x -C /tmp/v070
    cd /tmp/v070 && PYTHONPATH=. DATABASE_FILE=<repo>/backend/tests/fixtures/v0_7_0.db \
        python <repo>/backend/tests/fixtures/make_v0_7_0_db.py

Never regenerate it with current code: its value is that old code wrote it.
"""
import logging
logging.disable(logging.CRITICAL)
from datetime import datetime, timezone
from decimal import Decimal
from backend.database import create_tables, SessionLocal
from backend.services import transaction as svc

svc.get_btc_price = lambda ts, db: Decimal("50000")  # no network
create_tables()
db = SessionLocal()
def ts(s): return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)
rows = [
    dict(type="Deposit", timestamp=ts("2023-01-02T12:00:00"), from_account_id=99, to_account_id=1, amount=Decimal("50000"), fee_amount=Decimal("0"), fee_currency="USD", source="N/A"),
    dict(type="Buy", timestamp=ts("2023-01-10T12:00:00"), from_account_id=1, to_account_id=4, amount=Decimal("1.0"), fee_amount=Decimal("5"), fee_currency="USD", cost_basis_usd=Decimal("17000")),
    dict(type="Buy", timestamp=ts("2024-03-01T12:00:00"), from_account_id=1, to_account_id=4, amount=Decimal("0.5"), fee_amount=Decimal("5"), fee_currency="USD", cost_basis_usd=Decimal("31000")),
    dict(type="Transfer", timestamp=ts("2024-03-05T12:00:00"), from_account_id=4, to_account_id=2, amount=Decimal("0.6"), fee_amount=Decimal("0.0001"), fee_currency="BTC"),
    dict(type="Sell", timestamp=ts("2024-06-01T12:00:00"), from_account_id=4, to_account_id=3, amount=Decimal("0.3"), fee_amount=Decimal("10"), fee_currency="USD", gross_proceeds_usd=Decimal("20000")),
    dict(type="Deposit", timestamp=ts("2024-07-01T12:00:00"), from_account_id=99, to_account_id=2, amount=Decimal("0.01"), fee_amount=Decimal("0"), fee_currency="BTC", source="Income", cost_basis_usd=Decimal("620")),
    dict(type="Withdrawal", timestamp=ts("2025-02-01T12:00:00"), from_account_id=2, to_account_id=99, amount=Decimal("0.05"), fee_amount=Decimal("0"), fee_currency="BTC", purpose="Spent", proceeds_usd=Decimal("5000")),
]
for r in rows:
    svc.create_transaction_record(r, db)
db.close()
