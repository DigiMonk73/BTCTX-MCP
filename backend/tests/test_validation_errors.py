"""
A request the API's shapes refuse is a 422 with its reasons, less any input
JSON can't carry (main.validation_error_handler). A bare JSON number too
large for a float (1e999) is read as infinity, and NaN as NaN: FastAPI's own
422 echoed it back, which JSON can't write, so the answer was a 500 (#218).
Nothing was saved either way.
"""

import pytest

DEPOSIT = ('{"type": "Deposit", "timestamp": "2024-01-01T00:00:00Z", "from_account_id": 99, '
           '"to_account_id": 1, "source": "N/A", "amount": %s}')
ENTRY = ('{"rows": [{"type": "Deposit", "date": "2024-01-01", "from_account": "External", '
         '"to_account": "Wallet", "source": "MyBTC", "cost_basis_usd": "1", "amount": %s}]}')


def raw(client, url, text):
    return client.post(url, content=text, headers={"Content-Type": "application/json"})


def only_error(r) -> dict:
    assert r.status_code == 422, r.text
    [error] = r.json()["detail"]
    return error


@pytest.mark.parametrize("number", ["1e999", "-1e999", "NaN", "Infinity"])
def test_a_number_that_isnt_finite_is_a_422_without_it(auth_client, number):
    before = len(auth_client.get("/api/transactions").json())
    error = only_error(raw(auth_client, "/api/transactions", DEPOSIT % number))
    assert error["loc"] == ["body", "amount"] and error["type"] == "finite_number"
    assert "input" not in error
    assert len(auth_client.get("/api/transactions").json()) == before


def test_the_entry_import_too(auth_client):
    error = only_error(raw(auth_client, "/api/import/entries/preview", ENTRY % "1e999"))
    assert error["loc"] == ["body", "rows", 0, "amount"] and "input" not in error


def test_a_missing_field_whose_input_holds_one(auth_client):
    """The error for a missing field echoes the whole body around it."""
    error = only_error(raw(auth_client, "/api/import/entries/preview", '{"amount": 1e999}'))
    assert error["loc"] == ["body", "rows"] and "input" not in error


def test_an_input_json_can_carry_is_still_given(auth_client):
    error = only_error(raw(auth_client, "/api/transactions", DEPOSIT % '"lots"'))
    assert error["loc"] == ["body", "amount"] and error["input"] == "lots"
