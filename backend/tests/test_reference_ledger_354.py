"""
The reference ledger's 2.0 rows (2.0 spec 5.15; card B7a #354): its
`accounts` list adds two of each kind (wallets Coldcard and Jade, exchanges
Kraken and Overseas, banks Credit union and Savings), which
scripts/seed_ledger.py makes through the account API before the rows, and
its "since": "2.0" rows use only those, in 2026, but one: the split of a
pooled wallet, a Transfer from Wallet to the Coldcard with no fee, after
every row that takes coins from either.

- Every old row keeps its figures with the new rows beside it
  (test_old_rows_keep_their_figures): equivalence_check's ledgers leave the
  new rows out (B1), so this is their proof.
- The split row moves only Wallet's and the Coldcard's year-end lots and
  balances.
- The seed makes the accounts with the ids the ledger lists, uses again
  those a Delete All left, stops when an id comes out otherwise, and seeds
  given rows (a 1.x release's, make_reference_1x_db.py) without the account
  API, which a 1.x release lacks.
"""

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.models.exchange import Exchange
from backend.models.transaction import BitcoinLot, LotDisposal, Transaction
from backend.services import first_run, outbound
from backend.services.account import account_book
from backend.services.reports.form_8949 import disposal_box
from backend.services.tax_time import get_tax_timezone, local_date

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
WALLET, COLDCARD, EXTERNAL = 2, 100, 99
NEW_ACCOUNTS = set(range(100, 108))
USER, PASSWORD = "seed-user", "seed-password-123"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _script("seed_ledger")
reference_figures = _script("reference_figures")


def raw_rows() -> list[dict]:
    """The ledger's rows as written, with their notes."""
    return json.loads(seed_ledger.LEDGER.read_text())["transactions"]


def split_row() -> dict:
    [split] = [r for r in raw_rows() if "since" in r and r["from_account_id"] == WALLET]
    return split


@pytest.fixture
def owner(fresh_app, monkeypatch):
    """A fresh install claimed by the seed's login, price source Off; yields (client, Session)."""
    async def find_prices(day, full):
        raise AssertionError(f"a price was asked for: {day}")

    monkeypatch.setattr("backend.services.price_history.find_prices", find_prices)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    c = TestClient(app)
    seed_ledger.log_in(c, USER, PASSWORD, first_run.ensure_code())
    return c, fresh_app


def delete_all(c: TestClient) -> None:
    assert c.delete("/api/transactions/delete_all?confirm=DELETE").status_code == 204


def seed_without(c: TestClient, leave_out) -> list[dict]:
    """The ledger's rows (notes and all) but those `leave_out` picks, seeded
    after its accounts; returns the rows sent, in order."""
    kept = [(raw, sent) for raw, sent in zip(raw_rows(), seed_ledger.ledger_rows()) if not leave_out(raw)]
    seed_ledger.seed(c, [sent for _, sent in kept], seed_ledger.ledger_accounts())
    return [raw for raw, _ in kept]


def old_rows_figures(Session, sent: list[dict]) -> list[dict]:
    """Each 1.x row's figures, in the ledger's order: its own stored ones (a
    deposit's value at receipt is its income), every disposal it made
    (BTC, proceeds, basis, gain, term, box) and every lot it made (BTC,
    date, cost; not what's left of it, which the split row changes)."""
    with Session() as db:
        book, tz = account_book(db), get_tax_timezone(db)
        txs = db.query(Transaction).order_by(Transaction.id).all()
        assert len(txs) == len(sent)
        figures = []
        for tx, raw in zip(txs, sent):
            if "since" in raw:
                continue
            year = local_date(tx.timestamp, tz).year
            disposals = db.query(LotDisposal).filter(LotDisposal.transaction_id == tx.id)
            lots = db.query(BitcoinLot).filter(BitcoinLot.created_txn_id == tx.id)
            figures.append({
                "row": (tx.type, tx.timestamp, tx.from_account_id, tx.to_account_id, str(tx.amount)),
                "stored": [str(getattr(tx, f)) for f in ("cost_basis_usd", "proceeds_usd", "gross_proceeds_usd",
                                                         "realized_gain_usd", "holding_period", "fee_usd", "fmv_usd")],
                "disposals": sorted((str(d.disposed_btc), str(d.proceeds_usd_for_that_portion),
                                     str(d.disposal_basis_usd), str(d.realized_gain_usd), d.holding_period,
                                     bool(d.is_fee), disposal_box(d, year, tz, book)) for d in disposals),
                "lots": sorted((str(lot.total_btc), lot.acquired_date.isoformat(), str(lot.cost_basis_usd))
                               for lot in lots),
            })
        return figures


def test_old_rows_keep_their_figures(owner):
    c, Session = owner
    with_new = old_rows_figures(Session, seed_without(c, lambda raw: False))
    delete_all(c)
    alone = old_rows_figures(Session, seed_without(c, lambda raw: "since" in raw))
    assert len(alone) == len([r for r in raw_rows() if "since" not in r])
    assert with_new == alone


def test_the_new_rows_use_only_new_accounts_but_the_split():
    """2.0 spec 5.15: deposits from External fund them; the one exception
    is the split, from Wallet (and its date is checked, not trusted)."""
    new = [r for r in raw_rows() if "since" in r]
    assert {r["since"] for r in new} == {"2.0"}
    assert all({r["from_account_id"], r["to_account_id"]} <= NEW_ACCOUNTS | {EXTERNAL} for r in new if r != split_row())
    assert (split_row()["to_account_id"], split_row()["fee_amount"]) == (COLDCARD, "0")
    assert all(r["timestamp"].startswith("2026-") for r in new)  # so only 2026's figures move


def test_the_split_is_the_last_row_wallet_or_the_coldcard_names():
    """After every row that takes coins from either (or puts any in), so it
    moves only what each holds at the end."""
    split = split_row()
    naming = [r for r in raw_rows() if {WALLET, COLDCARD} & {r["from_account_id"], r["to_account_id"]}]
    assert max(r["timestamp"] for r in naming if r != split) < split["timestamp"]


def _without_holdings(year: dict) -> dict:
    return {**year, "report": {k: v for k, v in year["report"].items() if k != "end_of_year_balances"}}


def _holdings(year: dict, accounts: set[str], inside: bool) -> list[dict]:
    return [lot for lot in year["report"]["end_of_year_balances"] if (lot.get("account") in accounts) == inside]


def test_the_split_row_moves_only_wallets_and_the_coldcards_lots_and_balances(owner):
    c, Session = owner
    seed_without(c, lambda raw: False)
    with Session() as db:
        split = reference_figures.figures(db)
    delete_all(c)
    seed_without(c, lambda raw: raw == split_row())
    with Session() as db:
        unsplit = reference_figures.figures(db)

    for year in ("2023", "2024", "2025"):
        assert split["years"][year] == unsplit["years"][year], year
    after, before = split["years"]["2026"], unsplit["years"]["2026"]
    assert _without_holdings(after) == _without_holdings(before)  # every Form 8949 row, gain and income
    both = {"Wallet", "Coldcard"}
    assert _holdings(after, both, inside=False) == _holdings(before, both, inside=False)
    for column in ("quantity", "cost"):  # the same coins, only where they are differs
        assert sum(Decimal(str(lot[column])) for lot in _holdings(after, both, inside=True)) == \
            sum(Decimal(str(lot[column])) for lot in _holdings(before, both, inside=True)), column

    balances = {b["account_id"]: Decimal(b["balance"]) for b in split["dashboard"]["balances"]}
    unsplit_balances = {b["account_id"]: Decimal(b["balance"]) for b in unsplit["dashboard"]["balances"]}
    moved = Decimal(split_row()["amount"])
    assert (balances.pop(WALLET), balances.pop(COLDCARD)) == (unsplit_balances.pop(WALLET) - moved,
                                                              unsplit_balances.pop(COLDCARD) + moved)
    assert balances == unsplit_balances
    assert {k: v for k, v in split["dashboard"].items() if k != "balances"} == \
        {k: v for k, v in unsplit["dashboard"].items() if k != "balances"}


# The seed and the account API
def test_the_ledgers_accounts_are_made_with_their_ids(owner):
    c, Session = owner
    assert seed_ledger.seed(c) == len(raw_rows())
    listed = json.loads(seed_ledger.LEDGER.read_text())["accounts"]
    made = {a["id"]: (a["name"], a["kind"], a["currency"]) for a in c.get("/api/accounts/").json()}
    assert {a["id"]: (a["name"], a["kind"], a["currency"]) for a in listed}.items() <= made.items()
    with Session() as db:
        assert dict(db.query(Exchange.name, Exchange.sends_1099da)) == {
            "Exchange": True, "Kraken": True, "Overseas": False}


def test_seeding_again_after_delete_all_uses_the_accounts_left(owner):
    c, _ = owner
    seed_ledger.seed(c)
    before = c.get("/api/accounts/").json()
    delete_all(c)
    assert seed_ledger.seed(c) == len(raw_rows())
    assert [(a["id"], a["name"]) for a in c.get("/api/accounts/").json()] == [(a["id"], a["name"]) for a in before]


def test_seeding_again_puts_a_switch_changed_by_hand_back(owner):
    c, Session = owner
    seed_ledger.seed(c)
    assert c.put("/api/accounts/103", json={"sends_1099da": False}).status_code == 200  # Kraken's, by hand
    delete_all(c)
    seed_ledger.seed(c)
    with Session() as db:
        assert dict(db.query(Exchange.name, Exchange.sends_1099da))["Kraken"] is True


def test_an_account_that_would_get_another_id_stops_the_seed(owner):
    c, Session = owner
    assert c.post("/api/accounts/", json={"kind": "wallet", "name": "Spare"}).status_code == 201  # takes 100
    with pytest.raises(seed_ledger.SeedError, match="Coldcard is account 101 here"):
        seed_ledger.seed(c)
    with Session() as db:
        assert db.query(Transaction).count() == 0


def test_given_rows_alone_never_call_the_account_api(owner):
    """make_reference_1x_db.py seeds a 1.x release's app, which has no 2.0
    account API, with the ledger's 1.x rows."""
    c, _ = owner
    paths = []
    sent = c.request

    def noted(method, url, **kwargs):
        paths.append(str(url))
        return sent(method, url, **kwargs)

    c.request = noted
    rows = [sent_row for raw, sent_row in zip(raw_rows(), seed_ledger.ledger_rows()) if "since" not in raw]
    assert seed_ledger.seed(c, rows) == len(rows)
    assert paths and not [p for p in paths if "/api/accounts" in p]


def test_a_ledger_without_an_accounts_list_adds_none(tmp_path, monkeypatch):
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"transactions": []}))
    monkeypatch.setattr(seed_ledger, "LEDGER", ledger)
    assert seed_ledger.ledger_accounts() == []
