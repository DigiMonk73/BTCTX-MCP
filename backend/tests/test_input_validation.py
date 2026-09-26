"""
Input the ledger would record wrongly is rejected with a clear message
(hardening findings F12, F16, F27-F29, F33-F35, F39; docs/HARDENING_FINDINGS.md).
Each case here was accepted before, or failed with a 500.
"""

import pytest

from backend.tests.conftest import LOGIN_CREDS  # noqa: F401  (auth_client logs in with it)

BANK, WALLET, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 2, 3, 4, 99
TS = "2024-05-01T12:00:00Z"


@pytest.fixture(autouse=True)
def funded(auth_client):
    auth_client.delete("/api/transactions/delete_all")
    for body in (
        dict(type="Deposit", timestamp="2024-01-02T12:00:00Z", from_account_id=EXTERNAL, to_account_id=BANK,
             amount="100000", fee_amount="0", fee_currency="USD", source="N/A"),
        dict(type="Buy", timestamp="2024-01-03T12:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
             amount="1", cost_basis_usd="40000", fee_amount="0", fee_currency="USD"),
    ):
        assert auth_client.post("/api/transactions", json=body).status_code == 200
    yield
    auth_client.delete("/api/transactions/delete_all")


def post(client, **body):
    base = dict(timestamp=TS, fee_amount="0")
    return client.post("/api/transactions", json={**base, **body})


def deposit(**kw):
    return dict(type="Deposit", from_account_id=EXTERNAL, to_account_id=BANK, amount="100",
                fee_currency="USD", source="N/A", **kw)


def rejected(r, text):
    assert r.status_code == 422, (r.status_code, r.text)
    assert text in r.text, r.text


def test_huge_amount_is_refused_and_the_list_keeps_working(auth_client):
    rejected(post(auth_client, **{**deposit(), "amount": "1000000000000"}), "too large")
    assert auth_client.get("/api/transactions").status_code == 200


def test_exponent_notation_cant_skip_the_decimal_check(auth_client):
    rejected(post(auth_client, type="Deposit", from_account_id=EXTERNAL, to_account_id=WALLET,
                  amount="1E-9", fee_currency="BTC", source="MyBTC", cost_basis_usd="1"), "8 decimal places")


def test_usd_amounts_are_in_cents(auth_client):
    rejected(post(auth_client, **{**deposit(), "amount": "10.12345678"}), "2 decimal places")


def test_zero_negative_and_missing_amounts(auth_client):
    for amount in ("0", "-1", None):
        rejected(post(auth_client, **{**deposit(), "amount": amount}), "more than 0")


def test_negative_money_fields(auth_client):
    rejected(post(auth_client, type="Deposit", from_account_id=EXTERNAL, to_account_id=WALLET, amount="0.1",
                  fee_currency="BTC", source="MyBTC", cost_basis_usd="-500"), "can't be negative")
    rejected(post(auth_client, type="Sell", from_account_id=EXCH_BTC, to_account_id=EXCH_USD, amount="0.1",
                  gross_proceeds_usd="-5", fee_currency="USD"), "can't be negative")


def test_unknown_accounts(auth_client):
    rejected(post(auth_client, **{**deposit(), "to_account_id": 999}), "Unknown account id 999")
    rejected(post(auth_client, **{**deposit(), "to_account_id": 5}), "Unknown account id 5")  # BTC Fees


def test_missing_timestamp_is_a_422_not_a_500(auth_client):
    body = deposit()
    r = auth_client.post("/api/transactions", json={**body, "fee_amount": "0"})
    assert r.status_code == 422


def test_dates_before_bitcoin_or_in_the_future(auth_client):
    rejected(post(auth_client, **{**deposit(), "timestamp": "2008-06-01T00:00:00Z"}), "before Bitcoin")
    rejected(post(auth_client, **{**deposit(), "timestamp": "2099-01-01T00:00:00Z"}), "future")


def test_a_btc_withdrawal_needs_a_purpose(auth_client):
    """F12: without one it got $0 proceeds, a loss of its whole basis on 8949."""
    body = dict(type="Withdrawal", from_account_id=EXCH_BTC, to_account_id=EXTERNAL, amount="0.1",
                fee_currency="BTC")
    for purpose in (None, "N/A", "spnt"):
        rejected(post(auth_client, **body, purpose=purpose), "needs a purpose")
    # Any capitalization of a real purpose is stored in its canonical form.
    r = post(auth_client, **body, purpose="gift")
    assert r.status_code == 200 and r.json()["purpose"] == "Gift"


def test_a_sell_needs_proceeds_and_a_fee_below_them(auth_client):
    """F16: a sell without proceeds got $0 proceeds, a loss of its basis."""
    body = dict(type="Sell", from_account_id=EXCH_BTC, to_account_id=EXCH_USD, amount="0.1", fee_currency="USD")
    rejected(post(auth_client, **body), "needs its proceeds")
    rejected(post(auth_client, **body, gross_proceeds_usd="5", **{"fee_amount": "6"}), "more than its proceeds")
    assert post(auth_client, **body, proceeds_usd="5000").status_code == 200


def test_fee_currency_matches_the_account(auth_client):
    rejected(post(auth_client, type="Withdrawal", from_account_id=BANK, to_account_id=EXTERNAL, amount="10",
                  fee_currency="BTC", **{"fee_amount": "0.5"}), "must be in USD")


def test_a_partial_edit_is_checked_as_a_whole_transaction(auth_client):
    """F35: a PUT of just the account used to fail with 'Unknown transaction type: None'."""
    tx = post(auth_client, **deposit()).json()
    r = auth_client.put(f"/api/transactions/{tx['id']}", json={"to_account_id": EXCH_USD})
    assert r.status_code == 200, r.text
    assert r.json()["to_account_id"] == EXCH_USD
    rejected(auth_client.put(f"/api/transactions/{tx['id']}", json={"amount": "-5"}), "more than 0")
    rejected(auth_client.put(f"/api/transactions/{tx['id']}", json={"to_account_id": 42}), "Unknown account")


def test_messages_name_the_type_not_the_enum(auth_client):
    r = post(auth_client, type="Buy", from_account_id=BANK, to_account_id=EXCH_BTC, amount="0.1",
             cost_basis_usd="100", fee_currency="BTC", **{"fee_amount": "1"})
    assert r.status_code == 400 and "Buy => fee must be USD." in r.text and "TxType" not in r.text


def test_text_fields_have_a_limit(auth_client):
    rejected(post(auth_client, **{**deposit(), "source": "x" * 1000}), "too long")


def test_lowercase_gift_saved_before_normalizing_stays_off_form_8949(auth_client, test_engine):
    """F13: 8949 matched Gift/Donation/Lost case-sensitively; a 'gift' row
    (saved before input was normalized) printed with its basis and $0 gain."""
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    from backend.services.reports.form_8949 import build_form_8949_and_schedule_d

    tx = post(auth_client, type="Withdrawal", from_account_id=EXCH_BTC, to_account_id=EXTERNAL, amount="0.1",
              fee_currency="BTC", purpose="Gift").json()
    with test_engine.begin() as con:
        con.execute(text("UPDATE transactions SET purpose = 'gift' WHERE id = :id"), {"id": tx["id"]})
    assert auth_client.post("/api/transactions/recalculate").status_code == 200
    with sessionmaker(bind=test_engine)() as db:
        forms = build_form_8949_and_schedule_d(2024, db)
    assert forms["short_term"] == [] and forms["long_term"] == []
