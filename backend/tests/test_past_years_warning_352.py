"""
The past-year warning's answer (5.8, B6b-5: services/past_years.py): one
shape for every write it covers. `detail` stays a plain string, as every
error's is; the years, the changes, the pending ones and the fingerprint
come beside it. The 1099-DA switch's stub (B6c) answers with it too.
"""

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import account as account_service
from backend.services import past_years
from backend.tests.conftest import default_login

FILED = "which you may already have filed. Confirm to save it: a copy of your ledger is made first."


@pytest.mark.parametrize("years, text", [
    ([2025], "tax year 2025"),
    ([2024, 2025], "tax years 2024 and 2025"),
    ([2023, 2024, 2025], "tax years 2023, 2024 and 2025"),
])
def test_the_years_in_words(years, text):
    assert past_years.years_text(years) == text


def test_the_sentence_for_a_change_and_for_an_add_after_the_rest():
    assert past_years.warning_detail([2024, 2025]) == f"This changes the figures of tax years 2024 and 2025, {FILED}"
    assert past_years.warning_detail([2025], adds=True) == f"This adds to tax year 2025, {FILED}"


def test_the_fingerprint_is_a_sha256_of_its_parts_in_any_key_order():
    one = past_years.fingerprint({"kind": "edit", "data": {"a": 1, "b": 2}}, [2025])
    assert len(one) == 64 and int(one, 16) >= 0
    assert past_years.fingerprint({"data": {"b": 2, "a": 1}, "kind": "edit"}, [2025]) == one
    assert past_years.fingerprint({"kind": "edit", "data": {"a": 1, "b": 3}}, [2025]) != one
    assert past_years.fingerprint({"kind": "edit", "data": {"a": 1, "b": 2}}, [2024]) != one


def test_a_fingerprint_takes_dates_and_decimals_as_text():
    from datetime import datetime, timezone
    from decimal import Decimal

    when = datetime(2025, 3, 1, 12, tzinfo=timezone.utc)
    assert past_years.fingerprint({"at": when, "usd": Decimal("1.10")}) == past_years.fingerprint(
        {"at": str(when), "usd": "1.10"})


def test_the_409s_body():
    changes = [{"id": 7, "change": "Deleted.", "years": [2025]}]
    pending = [{"id": 3, "change": "gain 1.00 -> 2.00.", "years": [2024]}]
    asked = past_years.warning([2025], changes, pending, {"kind": "delete", "tx_id": 7})
    assert isinstance(asked, Exception) and str(asked) == asked.body["detail"]
    assert asked.body == {
        "detail": f"This changes the figures of tax year 2025, {FILED}",
        "years": [2025], "changes": changes, "pending": pending, "recalc_error": None,
        "confirm": past_years.fingerprint({"kind": "delete", "tx_id": 7}, [2025], changes, pending, None),
    }


def test_what_couldnt_be_worked_out_is_in_the_body_and_the_fingerprint():
    write = {"kind": "edit", "tx_id": 7}
    plain = past_years.warning([2025], [], [], write)
    stopped = past_years.warning([2025], [], [], write, recalc_error="Ledger not balanced for BTC")
    assert stopped.body["recalc_error"] == "Ledger not balanced for BTC"
    assert stopped.body["confirm"] != plain.body["confirm"]


def test_an_add_after_the_rest_says_so():
    assert past_years.warning([2025], [], [], {"kind": "add"}, adds=True).body["detail"] == (
        f"This adds to tax year 2025, {FILED}")


def test_the_1099da_switch_answers_with_the_same_warning(fresh_app, tax_year):
    c = TestClient(app)
    assert c.post("/api/login", json=default_login()).status_code == 200
    r = c.post("/api/transactions", json={
        "type": "Deposit", "timestamp": "2025-03-01T12:00:00Z", "from_account_id": 99, "to_account_id": 4,
        "amount": "1", "source": "MyBTC", "cost_basis_usd": "40000", "fee_amount": "0", "fee_currency": "BTC"})
    assert r.status_code == 200, r.text
    tax_year(2026)
    r = c.put("/api/accounts/4", json={"sends_1099da": False})
    assert r.status_code == 409
    assert set(r.json()) == {"detail", "years", "changes", "pending", "recalc_error", "confirm"}
    assert r.json()["detail"] == past_years.warning_detail([2025])
    assert not hasattr(account_service, "_years_text")  # one copy of the words
