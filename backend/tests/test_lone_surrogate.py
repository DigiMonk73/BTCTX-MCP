"""
Text with a lone surrogate ("\\ud800") anywhere in a JSON body (#313). JSON
allows one, but it isn't a character and UTF-8 can't encode it: SQLite
couldn't save it, and an answer quoting it couldn't be written, so these
routes answered with a server error. Every route now refuses it before it
runs, with a 422 naming the field. The login and the account routes keep
their own answer (a wrong login, #210: test_auth_input_edges.py).
"""

import json

import pytest

NOT_TEXT = "\ud800"
BANK, EXTERNAL = 1, 99


def send(client, method, url, body):
    """`body` as JSON with non-ASCII escaped, so a lone surrogate travels as
    JSON allows it (httpx's own encoding refuses it)."""
    return client.request(method, url, content=json.dumps(body), headers={"Content-Type": "application/json"})


def refused(r, field):
    assert (r.status_code, r.json()) == (
        422, {"detail": f"The {field} holds a character that isn't text (a lone surrogate): remove it."}), r.text


@pytest.fixture
def empty_ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_a_transaction_is_refused_not_a_server_error(auth_client, empty_ledger):
    r = send(auth_client, "POST", "/api/transactions", {
        "type": "Withdrawal", "timestamp": "2024-01-01T00:00:00Z", "from_account_id": BANK,
        "to_account_id": EXTERNAL, "amount": "1", "purpose": NOT_TEXT})
    refused(r, "purpose")
    assert auth_client.get("/api/transactions").json() == []


def test_an_entry_import_row_is_refused(auth_client, empty_ledger):
    r = send(auth_client, "POST", "/api/import/entries/preview", {"rows": [{"type": NOT_TEXT}]})
    refused(r, "type")


def test_a_tax_timezone_is_refused(auth_client):
    before = auth_client.get("/api/settings/tax-timezone").json()
    refused(send(auth_client, "PUT", "/api/settings/tax-timezone", {"timezone": NOT_TEXT}), "timezone")
    assert auth_client.get("/api/settings/tax-timezone").json() == before


def test_a_mempool_address_is_refused(auth_client):
    before = auth_client.get("/api/settings/network").json()
    r = send(auth_client, "PUT", "/api/settings/network",
             {"price_source": "mempool", "mempool_url": f"http://umbrel.local{NOT_TEXT}"})
    refused(r, "mempool_url")
    assert auth_client.get("/api/settings/network").json() == before


def test_a_key_that_isnt_text_names_its_field(auth_client):
    refused(send(auth_client, "PUT", "/api/settings/tax-timezone", {"timezone": "UTC", NOT_TEXT: 1}), "request")


def test_real_text_beyond_the_basic_plane_is_kept(auth_client, empty_ledger):
    """An emoji travels in JSON as a surrogate pair: one character, saved as typed."""
    r = send(auth_client, "POST", "/api/transactions", {
        "type": "Withdrawal", "timestamp": "2024-01-01T00:00:00Z", "from_account_id": BANK,
        "to_account_id": EXTERNAL, "amount": "1", "purpose": "Rent \U0001F3E0"})
    assert r.status_code == 200, r.text
    assert r.json()["purpose"] == "Rent \U0001F3E0"
