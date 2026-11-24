"""
A request the API's shapes refuse is a 422 with its reasons, less any input
JSON can't carry (main.validation_error_handler). A bare JSON number too
large for a float (1e999) is read as infinity, and NaN as NaN: FastAPI's own
422 echoed it back, which JSON can't write, so the answer was a 500 (#218).
Nothing was saved either way.
"""

import sys

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


# #954: a body nested about 1,000 to 10,000 levels deep (a few KB) made the
# handler's encoding recurse past Python's limit: a 500 where a 422 is due.
# Python 3.11's JSON parser refuses one past about 950 levels itself (a 400
# before validation); from 3.12 it reads them to about 10,000.
DEEP = "[" * 2000 + "]" * 2000
READS_DEEP = pytest.mark.skipif(sys.version_info < (3, 12), reason="3.11's parser refuses 2,000 levels: a 400")


@READS_DEEP
@pytest.mark.parametrize("url, body", [
    ("/api/login", '{"username": %s, "password": "x"}'),
    ("/api/users/register", '{"username": %s, "password": "a long enough password"}'),
    ("/api/users/reset-account", '{"username": %s, "password": "a long enough password"}'),
])
def test_a_deeply_nested_field_is_a_422_without_its_input(url, body):
    from fastapi.testclient import TestClient
    from backend.main import app
    r = raw(TestClient(app), url, body % DEEP)
    errors = [e for e in r.json()["detail"] if e["loc"] == ["body", "username"]] if r.status_code == 422 else []
    assert r.status_code == 422 and errors, r.text[:300]
    assert all("input" not in e and "ctx" not in e for e in errors)


@READS_DEEP
def test_a_deeply_nested_row_through_the_ai_key_is_a_422(auth_client, test_engine):
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import Session
    from backend.main import app
    from backend.services import ai_key
    with Session(test_engine) as db:
        ai_key.set_access(db, True)
        key = ai_key.create_key(db)
    r = TestClient(app).post("/api/import/entries/preview", content='{"rows": %s}' % ("[" * 2000 + "{}" + "]" * 2000),
                             headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    assert r.status_code == 422, r.text[:300]
    assert all("input" not in e for e in r.json()["detail"])


def test_no_depth_the_parser_reads_is_a_500():
    """Every depth near either Python's parser limit: a 422, or the parser's
    400, never a 500. On 3.11, 952 to 954 levels parsed and passed the
    check of each error alone, then failed the answer's own encoding, two
    levels deeper (#954's CI)."""
    from fastapi.testclient import TestClient
    from backend.main import app
    client = TestClient(app, raise_server_exceptions=False)
    for depth in [*range(900, 1001), *range(9950, 10001)]:
        nested = "[" * depth + "]" * depth
        r = raw(client, "/api/login", '{"username": %s, "password": "x"}' % nested)
        assert r.status_code in (400, 422), (depth, r.text[:200])
