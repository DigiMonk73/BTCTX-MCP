"""
The scripts that drive a running server confirm 2.0's past-year warning
(plan 5.8, 5.15): a write it answers with a 409 that gives a fingerprint
(`confirm`) is sent again, once, with `?confirm=<fingerprint>`; no switch
turns the warning off on a running server. scripts/seed_ledger.py (each row
of the reference test ledger) and scripts/smoke_test.py (each transaction it
creates), against a stand-in server: until the warning is built (B6b), no
save answers so. frontend/e2e/fixtures.ts has its own (past-year-confirm-568.e2e.ts).
"""

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
FINGERPRINT = "5f2d0c9b1e7a4c38a6d2b9e0f1c3a5d7e9b2c4d6f8a0b1c3d5e7f9a2b4c6d8e0"
ASKED = "This changes the figures of tax year 2024, which you may already have filed."


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")
smoke_test = _script("smoke_test")
HELPERS = pytest.mark.parametrize("send_confirmed", [seed_ledger.send_confirmed, smoke_test.send_confirmed],
                                  ids=["seed_ledger", "smoke_test"])


class StandIn:
    """A server that gives the next of `answers` to each request, keeping what it was sent."""

    def __init__(self, *answers: httpx.Response):
        self.answers = list(answers)
        self.seen: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return self.answers.pop(0)

    def client(self) -> httpx.Client:
        return httpx.Client(base_url="http://stand-in", transport=httpx.MockTransport(self))

    def sent(self) -> list[tuple[str, str, dict, object]]:
        """Each request as (method, path, query, JSON body)."""
        return [(r.method, r.url.path, dict(r.url.params), json.loads(r.content) if r.content else None)
                for r in self.seen]


def asks(fingerprint=FINGERPRINT) -> httpx.Response:
    """The warning's 409 (plan 5.8, step 3)."""
    return httpx.Response(409, json={"detail": ASKED, "years": [2024], "changes": [], "pending": [],
                                     "confirm": fingerprint})


def saved() -> httpx.Response:
    return httpx.Response(200, json={"id": 7})


@HELPERS
@pytest.mark.parametrize(("method", "path", "body"), [
    ("POST", "/api/transactions", {"type": "Buy", "timestamp": "2024-01-10T12:00:00Z"}),
    ("PUT", "/api/transactions/7", {"amount": "0.2"}),
    ("DELETE", "/api/transactions/7", None),
])
def test_a_409_that_asks_is_sent_again_with_its_fingerprint(send_confirmed, method, path, body):
    server = StandIn(asks(), saved())
    r = send_confirmed(server.client(), method, path, body)
    assert r.status_code == 200
    assert server.sent() == [(method, path, {}, body), (method, path, {"confirm": FINGERPRINT}, body)]


# Answers that don't ask: made afresh for each test, as a response is read once
OTHER_ANSWERS = {
    "saved": saved,
    # Delete All's 409 asks for a typed DELETE, never a fingerprint (services/wipe.py)
    "delete-all": lambda: httpx.Response(409, json={
        "detail": "Deletes all 3 transactions. To go ahead, confirm with DELETE.",
        "transactions": 3, "first_year": 2023, "last_year": 2024}),
    "no-fingerprint": lambda: httpx.Response(409, json={"detail": ASKED, "confirm": None}),
    "not-an-object": lambda: httpx.Response(409, json=[FINGERPRINT]),
    "not-json": lambda: httpx.Response(409, text="Conflict"),
    "not-a-409": lambda: httpx.Response(400, json={"detail": "Amount must be positive.", "confirm": FINGERPRINT}),
}


@HELPERS
@pytest.mark.parametrize("answer", OTHER_ANSWERS.values(), ids=OTHER_ANSWERS.keys())
def test_any_other_answer_comes_back_as_it_is(send_confirmed, answer):
    answer = answer()
    server = StandIn(answer)
    r = send_confirmed(server.client(), "POST", "/api/transactions", {"type": "Buy"})
    assert (r.status_code, r.content) == (answer.status_code, answer.content)
    assert len(server.seen) == 1


@HELPERS
def test_it_confirms_once(send_confirmed):
    """A second 409 (the ledger changed meanwhile, 5.8 step 4) goes to the
    caller: never a loop, never a confirm the caller didn't see asked."""
    server = StandIn(asks(), asks("0" * 64))
    r = send_confirmed(server.client(), "POST", "/api/transactions", {"type": "Buy"})
    assert r.status_code == 409 and r.json()["confirm"] == "0" * 64
    assert [query for _, _, query, _ in server.sent()] == [{}, {"confirm": FINGERPRINT}]


def test_seeding_confirms_each_row_that_asks():
    rows = [{"type": "Deposit", "timestamp": "2023-01-02T12:00:00Z"}, {"type": "Buy", "timestamp": "2023-01-10T12:00:00Z"}]
    server = StandIn(httpx.Response(200, json=[]), asks(), saved(), saved())
    assert seed_ledger.seed(server.client(), rows) == 2
    assert server.sent()[1:] == [("POST", "/api/transactions", {}, rows[0]),
                                 ("POST", "/api/transactions", {"confirm": FINGERPRINT}, rows[0]),
                                 ("POST", "/api/transactions", {}, rows[1])]


def test_seeding_stops_at_a_row_refused_after_its_confirm():
    server = StandIn(httpx.Response(200, json=[]), asks(), asks("0" * 64))
    with pytest.raises(seed_ledger.SeedError, match="row 1 .* refused: 409"):
        seed_ledger.seed(server.client(), [{"type": "Buy", "timestamp": "2023-01-10T12:00:00Z"}])


def test_the_smoke_test_confirms_what_it_creates():
    server = StandIn(asks(), saved())
    assert smoke_test.create(server.client(), type="Buy", timestamp="2024-01-10T12:00:00Z") == {"id": 7}
    assert [query for _, _, query, _ in server.sent()] == [{}, {"confirm": FINGERPRINT}]
