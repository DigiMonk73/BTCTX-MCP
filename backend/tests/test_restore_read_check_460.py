"""
A restore reads each transaction it brings back the way the screens and
reports read it, before the backup goes live (#460). Read only through the
database's models, a backup holding a value the app can't show (a broker
reporting or a type that isn't one of BitcoinTX's, an amount the reports
can't work with) was restored, and then the transaction list or the tax
report failed with an error. Such a backup is refused in plain words and
the live database stays as it was; a backup BitcoinTX made, old values the
app reads on purpose included, still restores and every page answers.

The helpers restore a real encrypted backup over a database of its own
(test_restore_checks.py).
"""

import pytest

from backend.tests.test_restore_checks import OWNER, _assert_refused, _backup, _logs_in, _restore
from backend.tests.test_restore_checks import live  # noqa: F401  (fixture)

DOESNT_FIT = ("Restore failed: This backup can't be restored: its {table} rows don't fit "
              "BitcoinTX's database.")
YEAR = 2024  # the backup's withdrawals and deposits below; IRS forms ship from 2024

# What a restored ledger must still show: the list, the dashboard's
# figures, the reports, Ledger Review
PAGES = (
    "/api/transactions",
    "/api/calculations/accounts/balances",
    "/api/calculations/average-cost-basis",
    "/api/calculations/gains-and-losses",
    f"/api/reports/complete_tax_report?year={YEAR}",
    f"/api/reports/irs_reports?year={YEAR}",
    f"/api/reports/simple_transaction_history?year={YEAR}",
    "/api/review",
)


def _pages_answer(client) -> dict:
    """Each page's status after a restore; the restore logged the browser out."""
    assert _logs_in(client, OWNER)
    return {page: client.get(page).status_code for page in PAGES}


@pytest.mark.parametrize("sql", [
    "UPDATE transactions SET broker_reporting = 'whatever'",  # the list: 500
    "UPDATE transactions SET type = 'Gift'",  # the list: 500, the tax report: 400
    "UPDATE transactions SET amount = 1e300",  # the tax report: 500
])
def test_a_value_the_screens_cant_show_is_refused(live, tmp_path, sql):  # noqa: F811
    _assert_refused(live, [sql], DOESNT_FIT.format(table="transactions"), tmp_path)


@pytest.mark.parametrize("table, sql", [
    ("transactions", "UPDATE transactions SET amount = 9e999"),  # stored as infinity
    ("transactions", "UPDATE transactions SET cost_basis_usd = -1e300"),
    ("transactions", "UPDATE transactions SET fee_usd = 1e18"),  # 19 digits before the point
    # The lots, disposals and ledger lines: the reports read them too
    ("bitcoin_lots", "UPDATE bitcoin_lots SET cost_basis_usd = 1e300"),
    ("lot_disposals", "INSERT INTO lot_disposals (lot_id, transaction_id, disposed_btc, realized_gain_usd, "
                      "disposal_basis_usd, proceeds_usd_for_that_portion, holding_period) "
                      "SELECT id, created_txn_id, 0.1, 1e300, 0, 0, 'SHORT' FROM bitcoin_lots"),
    ("ledger_entries", "UPDATE ledger_entries SET amount = 9e999"),
])
def test_a_number_the_reports_cant_use_is_refused(live, tmp_path, table, sql):  # noqa: F811
    """Finite, with at most 18 digits before the point (backup.NUMBERS_BELOW)."""
    _assert_refused(live, [sql], DOESNT_FIT.format(table=table), tmp_path)


@pytest.mark.parametrize("sql", [
    # A Spent withdrawal with a purpose saved before the input was checked (#342)
    "INSERT INTO transactions (type, timestamp, created_at, updated_at, from_account_id, to_account_id, "
    "amount, purpose, proceeds_usd, gross_proceeds_usd) VALUES ('Withdrawal', '2024-06-01 12:00:00', "
    "'2024-06-01 12:00:00', '2024-06-01 12:00:00', 4, 99, 0.1, ' gift ', 0, 0)",
    # A withdrawal of a purpose that isn't one of today's, read as Spent (#61)
    "INSERT INTO transactions (type, timestamp, created_at, updated_at, from_account_id, to_account_id, "
    "amount, purpose, proceeds_usd) VALUES ('Withdrawal', '2024-06-01 12:00:00', '2024-06-01 12:00:00', "
    "'2024-06-01 12:00:00', 4, 99, 0.1, 'Payment', 3000)",
    # A deposit of a source that isn't one of today's
    "INSERT INTO transactions (type, timestamp, created_at, updated_at, from_account_id, to_account_id, "
    "amount, source, cost_basis_usd) VALUES ('Deposit', '2024-06-01 12:00:00', '2024-06-01 12:00:00', "
    "'2024-06-01 12:00:00', 99, 2, 0.1, 'Mined', 3000)",
    # A tax timezone name saved before #407 (the restore keeps this install's)
    "INSERT INTO app_settings (key, value) VALUES ('tax_timezone', 'america/chicago')",
    # The biggest figures BitcoinTX writes: a 10-digit BTC amount, a 16-digit
    # USD basis, which its ledger line also holds; and 18 digits, the most
    "UPDATE transactions SET amount = 9999999999.99999, cost_basis_usd = 9999999999999999.99",
    "UPDATE ledger_entries SET amount = -9999999999999999.99 WHERE account_id = 1",
    "UPDATE transactions SET fee_usd = 1e17",
])
def test_values_bitcointx_reads_still_restore_and_every_page_answers(live, tmp_path, sql):  # noqa: F811
    blob, _ = _backup(tmp_path, sql)

    r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    assert _pages_answer(live.client) == dict.fromkeys(PAGES, 200)
