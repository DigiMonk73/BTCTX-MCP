"""
Text with a lone surrogate ("\\ud800") anywhere in a JSON body (#313). JSON
allows one, but it isn't a character and UTF-8 can't encode it: SQLite
couldn't save it, and an answer quoting it couldn't be written, so these
routes answered with a server error. Every route that takes a JSON body now
refuses it before it runs, with a 422 naming the field. The login and the
account routes keep their own answer (#210: test_auth_input_edges.py). A
backup's password, form data, is checked by its route.
"""

import json

import pytest
from fastapi.testclient import TestClient

from backend.main import app

NOT_TEXT = "\ud800"
BANK, EXTERNAL = 1, 99
# test_entry_import's BUY: a complete row, so only its type is wrong
BUY = {
    "date": "2023-01-10T15:00:00Z", "type": "Buy", "amount": "0.5",
    "from_account": "Bank", "to_account": "Exchange BTC",
    "cost_basis_usd": "10000.00", "fee_amount": "25.00", "fee_currency": "USD",
}
WITHDRAWAL = {"type": "Withdrawal", "timestamp": "2024-01-01T00:00:00Z", "from_account_id": BANK,
              "to_account_id": EXTERNAL, "amount": "1"}


def send(client, method, url, body, content_type="application/json"):
    """`body` as JSON with non-ASCII escaped, so a lone surrogate travels as
    JSON allows it (httpx's own encoding refuses it)."""
    return client.request(method, url, content=json.dumps(body), headers={"Content-Type": content_type})


def refused(r, field=None):
    detail = (f'The field "{field}" holds' if field else "The request holds") \
        + " a character that isn't text (a lone surrogate): remove it."
    assert (r.status_code, r.json()) == (422, {"detail": detail}), r.text


def multipart(fields, boundary, charset=""):
    """A multipart body by hand: (name, headers, value) parts, the boundary
    chosen (httpx picks its own), and the charset Starlette decodes its
    fields with."""
    parts = b"".join(
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"{extra}\r\n\r\n'.encode() + value + b"\r\n"
        for name, extra, value in fields)
    content_type = f"multipart/form-data; boundary={boundary}" + (f"; charset={charset}" if charset else "")
    return parts + f"--{boundary}--\r\n".encode(), {"Content-Type": content_type}


@pytest.fixture
def empty_ledger(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    yield
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")


def test_a_transaction_is_refused_not_a_server_error(auth_client, empty_ledger):
    refused(send(auth_client, "POST", "/api/transactions", {**WITHDRAWAL, "purpose": NOT_TEXT}), "purpose")
    assert auth_client.get("/api/transactions").json() == []


def test_the_media_type_is_read_in_any_case(auth_client, empty_ledger):
    r = send(auth_client, "POST", "/api/transactions", {**WITHDRAWAL, "purpose": NOT_TEXT}, "Application/JSON")
    refused(r, "purpose")


def test_an_entry_import_row_is_refused(auth_client, empty_ledger):
    refused(send(auth_client, "POST", "/api/import/entries/preview", {"rows": [{**BUY, "type": NOT_TEXT}]}), "type")


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


def test_the_refusal_names_the_field_in_a_few_words(auth_client):
    refused(send(auth_client, "PUT", "/api/settings/tax-timezone", {"timezone": "UTC", NOT_TEXT: 1}))
    refused(send(auth_client, "POST", "/api/import/entries/preview", {"rows": [NOT_TEXT]}), "rows")
    long_name = "x" * 100
    r = send(auth_client, "PUT", "/api/settings/tax-timezone", {"timezone": "UTC", long_name: [NOT_TEXT]})
    refused(r, "x" * 40 + "…")


def test_real_text_beyond_the_basic_plane_is_kept(auth_client, empty_ledger):
    """An emoji travels in JSON as a surrogate pair: one character, saved as typed."""
    r = send(auth_client, "POST", "/api/transactions", {**WITHDRAWAL, "purpose": "Rent \U0001F3E0"})
    assert r.status_code == 200, r.text
    assert r.json()["purpose"] == "Rent \U0001F3E0"


def test_a_route_without_a_json_body_is_left_alone():
    """The check reads only what the route reads: a body nested past what
    JSON parsing can follow, sent to the logout (which takes none), is no
    server error, and an upload whose boundary says "json" is read as the
    upload it is."""
    deep = TestClient(app).post("/api/logout", content="[" * 200_000, headers={"Content-Type": "application/json"})
    assert deep.status_code == 200, deep.text


def test_an_upload_whose_boundary_says_json_is_still_an_upload(auth_client):
    body, headers = multipart([("file", '; filename="t.csv"\r\nContent-Type: text/csv', b"date,type,amount\n")],
                              "json-boundary-json")
    plain_body, plain_headers = multipart([("file", '; filename="t.csv"\r\nContent-Type: text/csv',
                                            b"date,type,amount\n")], "plain-boundary")
    r = auth_client.post("/api/import/preview", content=body, headers=headers)
    plain = auth_client.post("/api/import/preview", content=plain_body, headers=plain_headers)
    assert (r.status_code, r.json()) == (plain.status_code, plain.json())


@pytest.mark.parametrize("url", ["/api/backup/download", "/api/backup/restore"])
def test_a_backup_password_that_isnt_text_is_refused(auth_client, url):
    """Form data: the request's charset (unicode_escape) can turn "\\ud800" into one."""
    fields = [("password", "", b"\\ud800")]
    if url.endswith("restore"):
        fields.append(("file", '; filename="b.btx"\r\nContent-Type: application/octet-stream', b"x"))
    body, headers = multipart(fields, "b0undary", charset="unicode_escape")
    r = auth_client.post(url, content=body, headers=headers)
    assert (r.status_code, r.json()) == (
        422, {"detail": "The password holds a character that isn't text (a lone surrogate): choose another."}), r.text
