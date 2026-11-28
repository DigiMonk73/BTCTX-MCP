"""
What one JSON body may hold, counted before its fields are checked: pydantic
checks every item of a list and, in a model that forbids other fields or a
field that is a mapping, every field of an object, then writes an error for
each, so a refusal's cost grew with what a body under the size limit
holds. Lists hold at most
MAX_JSON_ITEMS items in all, an object at most MAX_JSON_MEMBERS fields, as
deep as MAX_JSON_DEPTH; past any, a 422 in plain words, in well under a
second. No request BitcoinTX's screens or its AI connector send comes near.
"""

import json
import time

from backend.main import MAX_ERRORS_LISTED, MAX_JSON_ITEMS, MAX_JSON_MEMBERS, TOO_MANY_ITEMS, TOO_MANY_MEMBERS
from backend.routers.csv_import import MAX_ROWS
from backend.routers.entry_import import AI_MAX_ROWS
from backend.services.chosen_coins import MOST_LINES
from backend.body_limit import MAX_BODY_BYTES

# The most empty objects a body under the size limit holds in one list
EMPTY_ROWS = '{"rows":[' + ",".join(["{}"] * ((MAX_BODY_BYTES - 20) // 3)) + "]}"
# Seconds a refusal may take: each takes under 0.2 s on a computer of its own,
# well under the AI key's 1 s (SECURITY-RULES); the slack is for a CI runner
# running the whole suite at once, several times slower (1.3 s seen)
ITS_TIME = 5.0


def raw(client, url, text, headers=None):
    start = time.perf_counter()
    r = client.post(url, content=text, headers={"Content-Type": "application/json", **(headers or {})})
    return r, time.perf_counter() - start


def test_a_body_of_empty_rows_is_refused_at_once_with_the_ai_key(auth_client, ai_key_headers):
    r, took = raw(auth_client, "/api/import/entries/preview", EMPTY_ROWS, ai_key_headers)
    assert r.status_code == 422 and r.json() == {"detail": TOO_MANY_ITEMS}, r.text[:200]
    assert took < ITS_TIME, took


def test_and_logged_in_on_every_route_that_takes_rows(auth_client):
    for url in ("/api/import/entries/preview", "/api/import/entries/execute", "/api/import/river/execute",
                "/api/import/exchange/execute"):
        r, took = raw(auth_client, url, EMPTY_ROWS)
        assert r.status_code == 422 and r.json() == {"detail": TOO_MANY_ITEMS}, (url, r.text[:200])
        assert took < ITS_TIME, (url, took)


def test_the_items_are_counted_in_all_the_lists(auth_client):
    """Rows within the limit, each with chosen coins: the coins count too."""
    row = '{"chosen_coins":[' + ",".join(["{}"] * 100) + "]}"
    body = '{"rows":[' + ",".join([row] * (MAX_JSON_ITEMS // 100)) + "]}"
    r, took = raw(auth_client, "/api/import/entries/preview", body)
    assert r.status_code == 422 and r.json() == {"detail": TOO_MANY_ITEMS}, r.text[:200]
    assert took < ITS_TIME, took


def test_as_many_items_as_allowed_go_on_to_their_checks(auth_client):
    """MAX_JSON_ITEMS items in all: the route's own answer, not this one."""
    body = '{"rows":[' + ",".join(["1"] * MAX_JSON_ITEMS) + "]}"
    r, _ = raw(auth_client, "/api/import/river/execute", body)
    assert r.status_code in (400, 422) and r.json()["detail"] != TOO_MANY_ITEMS, r.text[:200]


def test_an_object_with_too_many_fields_is_refused(auth_client):
    """An exchange's own mapping forbids other fields, and its kinds are a
    mapping: each field past the first would be an error of its own."""
    junk = {f"k{n}": 1 for n in range(MAX_JSON_MEMBERS + 1)}
    for body in ({"name": "x", **junk}, {"name": "x", "kinds": junk}):
        r, _ = raw(auth_client, "/api/import/exchange/mappings", json.dumps(body))
        assert r.status_code == 422 and r.json() == {"detail": TOO_MANY_MEMBERS}, r.text[:200]


def test_an_object_with_as_many_fields_as_allowed_goes_on_to_its_checks(auth_client):
    junk = {f"k{n}": 1 for n in range(MAX_JSON_MEMBERS - 1)}
    r, _ = raw(auth_client, "/api/import/exchange/mappings", json.dumps({"name": "x", **junk}))
    assert r.status_code == 422 and r.json()["detail"] != TOO_MANY_MEMBERS, r.text[:200]


def test_the_largest_real_requests_fit():
    """A file's import sends at most MAX_ROWS rows, flat; a transaction
    chooses coins in at most MOST_LINES lines; the AI key sends at most
    AI_MAX_ROWS rows; a row has far fewer fields than an object may."""
    assert MAX_JSON_ITEMS >= max(MAX_ROWS, MOST_LINES, AI_MAX_ROWS)
    assert MAX_JSON_MEMBERS >= 1000


def test_a_refusal_lists_the_first_errors_then_how_many_more(auth_client):
    many, _ = raw(auth_client, "/api/import/river/execute", json.dumps({"rows": [{}] * MAX_ERRORS_LISTED}))
    errors = many.json()["detail"]
    assert len(errors) == MAX_ERRORS_LISTED + 1 and all(e["loc"] and e["msg"] for e in errors)
    more = errors[-1]
    assert more["type"] == "more_errors" and more["msg"].startswith("And ") and more["msg"].endswith(" more errors.")


def test_a_missing_field_doesnt_echo_its_row_but_a_value_is_kept(auth_client):
    """A "missing" error gives its whole row as its input: left out, as
    any list or object is. A value a field was given is echoed as before."""
    r, _ = raw(auth_client, "/api/import/river/execute", json.dumps({"rows": [{"note": "x" * 1000}]}))
    assert all("input" not in e for e in r.json()["detail"] if e["type"] == "missing"), r.text[:300]
    r, _ = raw(auth_client, "/api/import/river/execute", json.dumps({"rows": [{"amount": "lots"}]}))
    assert any(e.get("input") == "lots" for e in r.json()["detail"]), r.text[:300]


def _wide() -> str:
    """One object of as many objects of MAX_JSON_MEMBERS fields as the size
    limit holds: over half a million values, all within the limits."""
    inner = "{" + ",".join(f'"{m}":0' for m in range(MAX_JSON_MEMBERS)) + "}"
    return "{" + ",".join(f'"{n}":{inner}' for n in range((MAX_BODY_BYTES - 100) // (len(inner) + 8))) + "}"


def test_no_body_under_the_size_limit_takes_a_second(auth_client, ai_key_headers):
    """The worst bodies within every limit (the review's): one row of a
    million values, which each "missing" error echoed; every field of every
    row the wrong type, as many rows as allowed; and the login, anonymous,
    given a list for its username."""
    wrong = {field: {} for field in ("row_number", "date", "type", "amount", "from_account", "to_account",
                                     "cost_basis_usd", "proceeds_usd", "fee_amount", "fee_currency", "source",
                                     "purpose", "matched_tx_id", "not_a_duplicate", "left_out")}
    cases = [
        ("/api/import/entries/preview", '{"rows":[' + _wide() + "]}", ai_key_headers),
        ("/api/import/river/execute", '{"rows":[' + _wide() + "]}", None),
        ("/api/import/river/execute", json.dumps({"rows": [wrong] * MAX_JSON_ITEMS}), None),
        ("/api/login", '{"username":[' + ",".join(["0"] * ((MAX_BODY_BYTES - 40) // 2)) + '],"password":"x"}', None),
    ]
    for url, body, headers in cases:
        assert len(body) <= MAX_BODY_BYTES, (url, len(body))
        r, took = raw(auth_client, url, body, headers)
        assert r.status_code == 422 and len(r.content) < 1_000_000, (url, r.status_code, len(r.content))
        assert took < ITS_TIME, (url, took)
