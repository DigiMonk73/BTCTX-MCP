"""
A dollar withdrawal holds no bitcoin purpose and no value (#449). The form
kept a Purpose and an FMV chosen for a bitcoin account after the
account was changed to Bank, and saved them; the Complete Tax Report then
listed the dollar withdrawal as a gift of bitcoin (its dollars shown as BTC,
with the typed value, in the section's total), and a leftover Spent with
proceeds was counted in the dashboard's spent total.

The save now drops them, on a new transaction and on an edit (a label of
its own, such as "Rent", stays), and the report, the dashboard, Ledger Review
and the AI's duplicate check read them only on a withdrawal of bitcoin, so
rows saved before the fix are left out too.
"""

import csv
import io

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from backend.services.reports.reporting_core import generate_report_data

BANK, WALLET, EXCHANGE_USD, EXTERNAL = 1, 2, 3, 99
DOLLAR_ACCOUNTS = [BANK, EXCHANGE_USD]
BTC_ONLY = ("purpose", "proceeds_usd", "gross_proceeds_usd", "fmv_usd")


def _post(client, **tx):
    r = client.post("/api/transactions", json={"fee_amount": "0", "fee_currency": "USD", **tx})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def ledger(auth_client, test_engine):
    """Dollars in Bank and Exchange USD, a bitcoin in the Wallet."""
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    for account in DOLLAR_ACCOUNTS:
        _post(auth_client, type="Deposit", timestamp="2026-01-05T12:00:00Z", from_account_id=EXTERNAL,
              to_account_id=account, amount="2000", source="N/A")
    _post(auth_client, type="Deposit", timestamp="2026-01-06T12:00:00Z", from_account_id=EXTERNAL,
          to_account_id=WALLET, amount="1", fee_currency="BTC", source="MyBTC", cost_basis_usd="30000")
    yield sessionmaker(bind=test_engine)
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def _insert_old_row(engine, tx_id, account, purpose, *, fmv=None, proceeds=None):
    """A dollar withdrawal as versions up to 1.2.8 saved it from the form: a
    purpose (and its value) left from the bitcoin fields the form hid."""
    with engine.begin() as con:
        con.execute(text(
            "INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount, fee_amount,"
            " fee_currency, purpose, fmv_usd, proceeds_usd, gross_proceeds_usd)"
            " VALUES (:id, 'Withdrawal', '2026-03-01T12:00:00Z', :account, 99, '100', '0', 'USD', :purpose,"
            " :fmv, :proceeds, :proceeds)"),
            dict(id=tx_id, account=account, purpose=purpose, fmv=fmv, proceeds=proceeds))


def _stored(engine, tx_id):
    with engine.connect() as con:
        return con.execute(text(
            "SELECT purpose, proceeds_usd, gross_proceeds_usd, fmv_usd, proceeds_from_price, fmv_from_price"
            " FROM transactions WHERE id = :id"), {"id": tx_id}).one()


@pytest.mark.parametrize("account", DOLLAR_ACCOUNTS)
@pytest.mark.parametrize("purpose", ["Gift", "Donation", "Lost", "Spent"])
def test_a_dollar_withdrawal_is_saved_without_a_purpose_or_value(auth_client, ledger, account, purpose):
    # What the form sent after Bitcoin Wallet, a purpose and its value, then Bank (#449's steps)
    saved = _post(auth_client, type="Withdrawal", timestamp="2026-03-01T12:00:00Z", from_account_id=account,
                  to_account_id=EXTERNAL, amount="100", purpose=purpose, fmv_usd="500", proceeds_usd="500")
    listed = next(t for t in auth_client.get("/api/transactions").json() if t["id"] == saved["id"])
    for tx in (saved, listed):
        assert {key: tx[key] for key in BTC_ONLY} == dict.fromkeys(BTC_ONLY), tx
        assert tx["fmv_from_price"] is False and tx["proceeds_from_price"] is False


def test_a_dollar_withdrawal_is_not_in_the_tax_reports_gifts(auth_client, ledger):
    _post(auth_client, type="Withdrawal", timestamp="2026-03-01T12:00:00Z", from_account_id=BANK,
          to_account_id=EXTERNAL, amount="100", purpose="Gift", fmv_usd="500")
    with ledger() as db:
        assert generate_report_data(db, 2026)["gifts_donations_lost"] == []


def test_a_dollar_withdrawal_is_not_in_the_dashboards_spent_total(auth_client, ledger):
    # Sweep S1's steps on #449
    _post(auth_client, type="Withdrawal", timestamp="2026-03-01T12:00:00Z", from_account_id=BANK,
          to_account_id=EXTERNAL, amount="100", purpose="Spent", proceeds_usd="500")
    assert auth_client.get("/api/calculations/gains-and-losses").json()["withdrawals_spent"] == 0


def test_a_bitcoin_withdrawal_keeps_its_purpose_and_value(auth_client, ledger):
    gift = _post(auth_client, type="Withdrawal", timestamp="2026-03-01T12:00:00Z", from_account_id=WALLET,
                 to_account_id=EXTERNAL, amount="0.01", fee_currency="BTC", purpose="Gift", fmv_usd="500")
    spend = _post(auth_client, type="Withdrawal", timestamp="2026-03-02T12:00:00Z", from_account_id=WALLET,
                  to_account_id=EXTERNAL, amount="0.01", fee_currency="BTC", purpose="Spent", proceeds_usd="450")
    assert (gift["purpose"], gift["fmv_usd"]) == ("Gift", "500.00")
    assert (spend["purpose"], spend["gross_proceeds_usd"]) == ("Spent", "450.00")


@pytest.fixture
def old_rows(auth_client, test_engine, ledger):
    """Each kind of dollar withdrawal 1.2.8 could save, beside a bitcoin gift and spend that count."""
    _insert_old_row(test_engine, 901, BANK, "Gift", fmv="500")
    _insert_old_row(test_engine, 902, EXCHANGE_USD, "Donation", fmv="250")
    _insert_old_row(test_engine, 903, BANK, "Lost")
    _insert_old_row(test_engine, 904, BANK, "Spent", proceeds="500")
    _insert_old_row(test_engine, 905, EXCHANGE_USD, "Spent", proceeds="0")
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    _post(auth_client, type="Withdrawal", timestamp="2026-04-01T12:00:00Z", from_account_id=WALLET,
          to_account_id=EXTERNAL, amount="0.01", fee_currency="BTC", purpose="Gift", fmv_usd="600")
    _post(auth_client, type="Withdrawal", timestamp="2026-04-02T12:00:00Z", from_account_id=WALLET,
          to_account_id=EXTERNAL, amount="0.01", fee_currency="BTC", purpose="Spent", proceeds_usd="450")
    return ledger


def test_the_report_lists_only_the_bitcoin_gift(old_rows):
    with old_rows() as db:
        gifts = generate_report_data(db, 2026)["gifts_donations_lost"]
    assert [(g["type"], g["amount"], g["fmv_usd"]) for g in gifts] == [("Gift", 0.01, 600.0)]


def test_the_dashboard_counts_only_the_bitcoin_spend(auth_client, old_rows):
    assert auth_client.get("/api/calculations/gains-and-losses").json()["withdrawals_spent"] == 450


def test_ledger_review_lists_none_of_the_dollar_withdrawals(auth_client, old_rows):
    review = auth_client.get("/api/review").json()
    listed = {item["id"] for check in review["checks"] for item in check["items"]}
    assert listed.isdisjoint({901, 902, 903, 904, 905}), review["checks"]


def test_an_edit_of_an_old_row_drops_them(auth_client, test_engine, old_rows):
    # Any edit, here the amount alone, saves the row as a dollar withdrawal is saved now
    r = auth_client.put("/api/transactions/901", json={"amount": "90"})
    assert r.status_code == 200, r.text
    assert _stored(test_engine, 901) == (None, None, None, None, False, False)
    r = auth_client.put("/api/transactions/904", json={"amount": "90"})
    assert r.status_code == 200, r.text
    assert _stored(test_engine, 904) == (None, None, None, None, False, False)


def test_moving_a_bitcoin_gift_to_bank_drops_them(auth_client, test_engine, ledger):
    gift = _post(auth_client, type="Withdrawal", timestamp="2026-03-01T12:00:00Z", from_account_id=WALLET,
                 to_account_id=EXTERNAL, amount="0.01", fee_currency="BTC", purpose="Gift")
    assert gift["fmv_from_price"] is True  # priced at the stubbed price
    r = auth_client.put(f"/api/transactions/{gift['id']}", json={"from_account_id": BANK, "fee_currency": "USD"})
    assert r.status_code == 200, r.text
    assert _stored(test_engine, gift["id"]) == (None, None, None, None, False, False)


def test_the_csv_export_of_an_old_row_still_imports(auth_client, test_engine, old_rows):
    exported = auth_client.get("/api/backup/csv").text
    rows = list(csv.DictReader(io.StringIO(exported)))
    assert any(r["from_account"] == "Bank" and r["purpose"] == "Gift" for r in rows), rows
    assert auth_client.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204
    files = {"file": ("export.csv", exported.encode(), "text/csv")}
    preview = auth_client.post("/api/import/preview", files=files).json()
    assert preview["can_import"] and preview["errors"] == [], preview
    r = auth_client.post("/api/import/execute", files=files)
    assert r.status_code == 200, r.text
    assert r.json()["imported_count"] == len(rows)
    dollars = [t for t in auth_client.get("/api/transactions").json()
               if t["type"] == "Withdrawal" and t["from_account_id"] in DOLLAR_ACCOUNTS]
    assert len(dollars) == 5
    assert all({key: t[key] for key in BTC_ONLY} == dict.fromkeys(BTC_ONLY) for t in dollars), dollars
    with old_rows() as db:
        assert [g["amount"] for g in generate_report_data(db, 2026)["gifts_donations_lost"]] == [0.01]


AI_ROW = {"date": "2026-03-01T12:00:00Z", "type": "Withdrawal", "amount": "100", "from_account": "Bank",
          "to_account": "External", "fee_amount": "0", "fee_currency": "USD"}


def test_the_ai_sending_a_dollar_withdrawal_again_saves_it_once(auth_client, ledger):
    """The duplicate check compares purposes: the one sent isn't the none saved."""
    row = dict(AI_ROW, purpose="Spent", proceeds_usd="500")
    first = auth_client.post("/api/import/entries/execute", json={"rows": [row]}).json()
    assert first["imported_count"] == 1, first
    again = auth_client.post("/api/import/entries/execute", json={"rows": [row]}).json()
    assert (again["imported_count"], again["skipped_duplicates"]) == (0, 1), again


def test_an_old_rows_leftover_purpose_doesnt_hide_it_from_the_ai(auth_client, old_rows):
    preview = auth_client.post("/api/import/entries/preview", json={"rows": [AI_ROW]}).json()
    [result] = preview["results"]
    assert result["status"] == "duplicate" and result["matched_transaction_id"] in (901, 903, 904), result


def test_a_dollar_withdrawals_own_label_is_kept(auth_client, test_engine, ledger):
    """Any other text is a label a dollar withdrawal may carry (the CSV guide
    says so, #304): kept, its values still dropped, and kept through an edit."""
    saved = _post(auth_client, type="Withdrawal", timestamp="2026-03-01T12:00:00Z", from_account_id=BANK,
                  to_account_id=EXTERNAL, amount="100", purpose="Rent", fmv_usd="500")
    assert (saved["purpose"], saved["fmv_usd"]) == ("Rent", None)
    r = auth_client.put(f"/api/transactions/{saved['id']}", json={"amount": "90"})
    assert r.status_code == 200, r.text
    assert _stored(test_engine, saved["id"])[0] == "Rent"
    with ledger() as db:
        assert generate_report_data(db, 2026)["gifts_donations_lost"] == []


def test_an_old_spaced_bitcoin_purpose_is_dropped_too(auth_client, test_engine, ledger):
    """A purpose saved before 0.9.2 as typed (" gift ", #342) is a bitcoin one all the same."""
    _insert_old_row(test_engine, 906, BANK, " gift ", fmv="500")
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    r = auth_client.put("/api/transactions/906", json={"amount": "90"})
    assert r.status_code == 200, r.text
    assert _stored(test_engine, 906) == (None, None, None, None, False, False)
