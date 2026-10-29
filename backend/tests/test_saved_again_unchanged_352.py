"""
Every row of the reference test ledger saved again unchanged, through the
past-year warning's path (2.0 spec 5.15; card B6b #352): the edit split from
its commit, the dry run on a scratch copy, and the save. With every row in
an earlier tax year (this tax year is 2027 here), each goes through the dry
run, and nothing may move, so none asks: every disposal's proceeds, basis,
gain, box, term and date acquired, every lot made, every stored figure.

Each of the two runs saves every row in turn, in parts that run side by
side (#814): a part takes its share of the rows, in their order, on a
ledger of its own, and the parts together take every row once.
"""

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import first_run, outbound, year_changes
from backend.services.tax_time import get_tax_timezone


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[2] / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")


@pytest.fixture
def seeded(fresh_app, monkeypatch):
    """The reference ledger in a fresh install, as test_seed_ledger seeds it
    but for #715's rows valued from a stored price (the seed's default)."""
    async def find_prices(day, full):
        return {}, False

    monkeypatch.setattr("backend.services.price_history.find_prices", find_prices)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    client = TestClient(app)
    seed_ledger.log_in(client, "seed-user", "seed-password-123", first_run.ensure_code())
    seed_ledger.seed(client)
    return client, fresh_app


def figures(Session) -> dict:
    """Every row's that has figures of a tax year (year_changes.counts). A
    dollar deposit's basis means nothing: an edit that sends its amount
    stores the 0.00 its add left blank, as 1.x's edits always have."""
    with Session() as db:
        return {tx_id: row for tx_id, row in year_changes.figures(db, get_tax_timezone(db)).items()
                if year_changes.counts(row)}


def save_again(client, tx_id: int, body: dict) -> None:
    """Saved at once: moving nothing, it never asks."""
    r = client.put(f"/api/transactions/{tx_id}", json=body)
    assert r.status_code == 200, (tx_id, r.text)


# About 27 rows a part, so a part takes under a minute on CI
PARTS = 8


def part_of(txs: list, part: int) -> list:
    """Part `part`'s rows: its share of the list, in their order."""
    size = -(-len(txs) // PARTS)
    return txs[part * size:(part + 1) * size]


def test_the_parts_take_every_row_once_in_order():
    for count in (1, PARTS - 1, PARTS, 213, 214):
        txs = list(range(count))
        assert [tx for part in range(PARTS) for tx in part_of(txs, part)] == txs


@pytest.mark.slow
@pytest.mark.parametrize("part", range(PARTS))
def test_every_reference_row_saved_again_unchanged_keeps_its_figures(seeded, tax_year, part):
    client, Session = seeded
    before = figures(Session)
    tax_year(2027)
    rows = part_of(client.get("/api/transactions").json(), part)
    assert rows
    for tx in rows:
        save_again(client, tx["id"], {})
    assert figures(Session) == before


@pytest.mark.slow
@pytest.mark.parametrize("part", range(PARTS))
def test_and_with_its_own_date_and_amount_sent_back(seeded, tax_year, part):
    client, Session = seeded
    before = figures(Session)
    tax_year(2027)
    rows = part_of(client.get("/api/transactions").json(), part)
    assert rows
    for tx in rows:
        save_again(client, tx["id"], {"timestamp": tx["timestamp"], "amount": tx["amount"]})
    assert figures(Session) == before
