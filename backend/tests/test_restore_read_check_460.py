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


PRICE = "INSERT OR REPLACE INTO btc_price_daily (day, usd, source) VALUES ('{day}', {usd}, 'bitstamp')"
SALE = ("INSERT INTO transactions (type, timestamp, created_at, updated_at, from_account_id, to_account_id, amount, "
        "proceeds_usd, gross_proceeds_usd, cost_basis_usd, realized_gain_usd) VALUES ('Sell', '2024-06-01 12:00:00', "
        "'2024-06-01 12:00:00', '2024-06-01 12:00:00', 4, 3, 1, 1000, 1000, {basis}, -{basis})")


@pytest.mark.parametrize("table, sql", [
    ("transactions", "UPDATE transactions SET amount = 9e999"),  # stored as infinity
    ("transactions", "UPDATE transactions SET cost_basis_usd = -1e300"),
    ("transactions", "UPDATE transactions SET fee_usd = 1e17"),  # 18 digits before the point
    # A buy of a satoshi: the dashboard's average cost (its basis over its bitcoin)
    # failed once a recalculation had made its lot (#483's re-check)
    ("transactions", "UPDATE transactions SET amount = 0.00000001, cost_basis_usd = 9e21"),
    ("transactions", SALE.format(basis="1e22")),  # a sale's totals: 23 digits
    ("transactions", "UPDATE transactions SET fee_amount = 1e10"),  # 11: past the save's BTC rule
    # The lots, disposals, ledger lines and prices: the reports read them too
    ("bitcoin_lots", "UPDATE bitcoin_lots SET cost_basis_usd = 1e300"),
    ("bitcoin_lots", "UPDATE bitcoin_lots SET remaining_btc = 1e10"),
    ("bitcoin_lots", "UPDATE bitcoin_lots SET remaining_btc = 0.00000001, cost_basis_usd = 1e17"),
    ("lot_disposals", "INSERT INTO lot_disposals (lot_id, transaction_id, disposed_btc, realized_gain_usd, "
                      "disposal_basis_usd, proceeds_usd_for_that_portion, holding_period) "
                      "SELECT id, created_txn_id, 0.1, 1e300, 0, 0, 'SHORT' FROM bitcoin_lots"),
    ("ledger_entries", "UPDATE ledger_entries SET amount = 9e999"),
    ("btc_price_daily", PRICE.format(day="2024-01-01", usd="1e15")),  # times a lot, past what the reports round
])
def test_a_number_the_reports_cant_use_is_refused(live, tmp_path, table, sql):  # noqa: F811
    """Finite, and within its kind's limit (backup.NUMBER_LIMITS)."""
    _assert_refused(live, [sql], DOESNT_FIT.format(table=table), tmp_path)


@pytest.mark.parametrize("table, sql", [
    # Year 1 in UTC is the year before in America/Chicago: the tax report failed (OverflowError)
    ("transactions", "UPDATE transactions SET timestamp = '0001-01-01T00:30:00Z'"),
    ("transactions", "UPDATE transactions SET acquired_at = '0001-01-01'"),
    ("bitcoin_lots", "UPDATE bitcoin_lots SET acquired_date = '9999-12-31T23:00:00Z'"),  # Ledger Review: 422
])
def test_a_date_outside_the_reports_years_is_refused(live, tmp_path, table, sql):  # noqa: F811
    """Years 2 to 9998 (backup.USABLE_YEARS): a timezone can't move them past Python's."""
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
    # The biggest figures a save takes: a 10-digit BTC amount, a 16-digit USD
    # basis, which its ledger line also holds
    "UPDATE transactions SET amount = 9999999999.99999, cost_basis_usd = 9999999999999999.99",
    "UPDATE ledger_entries SET amount = -9999999999999999.99 WHERE account_id = 1",
    # A buy of a satoshi at 17 digits, the most a dollar figure may have
    "UPDATE transactions SET amount = 0.00000001, cost_basis_usd = 99999999999999984",
    # A sale's basis over many lots at a save's limit, past 16 digits (#483's review:
    # 120 lots gave 1.08e18); 22 digits, the most a sale's totals may have
    SALE.format(basis="9e21"),
    # A buy at the BTC rule's limit, held when 2024 begins and ends, times a price
    # just below its own (the tax report rebuilds the lots from the buy; at $9.9e17
    # it failed, InvalidOperation)
    ("UPDATE transactions SET amount = 9999999999",
     PRICE.format(day="2024-01-01", usd="9.99e14"), PRICE.format(day="2025-01-01", usd="9.99e14")),
])
def test_values_bitcointx_reads_still_restore_and_every_page_answers(live, tmp_path, sql):  # noqa: F811
    """And again once Recalculate Ledger has rebuilt the lots from the transactions."""
    blob, _ = _backup(tmp_path, *((sql,) if isinstance(sql, str) else sql))

    r = _restore(live.client, blob)

    assert r.status_code == 200, r.text
    assert _pages_answer(live.client) == dict.fromkeys(PAGES, 200)
    assert live.client.post("/api/transactions/recalculate").status_code == 200
    assert {page: live.client.get(page).status_code for page in PAGES} == dict.fromkeys(PAGES, 200)


@pytest.mark.parametrize("sql, said", [
    ("UPDATE transactions SET broker_reporting = 'whatever'", "transactions can't be shown: broker_reporting"),
    ("UPDATE transactions SET fee_usd = 123456789012345678901234", "transactions.fee_usd is bigger than "
                                                                    "BitcoinTX's figures"),
])
def test_the_log_says_which_column_never_its_value(live, tmp_path, caplog, sql, said):  # noqa: F811
    """A column's name is words the code chose; the backup's value stays out of the log."""
    blob, _ = _backup(tmp_path, sql)

    assert _restore(live.client, blob).status_code == 400
    refused = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Restore refused")]
    assert refused == [f"Restore refused: a transactions row can't be read ({said})"]
    assert "whatever" not in caplog.text and "123456789" not in caplog.text
