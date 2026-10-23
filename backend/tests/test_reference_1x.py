"""
An upgraded 1.x ledger (2.0 spec 5.15): fixtures/reference_1x.db is the
reference test ledger as the last 1.x release (make_reference_1x_db.RELEASE)
saved it, seeded by that release's own code, with 1.x's latest figures for
it beside it (fixtures/reference_1x_figures.json: those of the develop
commit 2.0 last took in, since develop may have fixed figures since the
release). A copy migrated to this code's head and recalculated, as a user's
first edit after upgrading would, must give the same figures.
fixtures/make_reference_1x_db.py makes both again, when a develop merge
brings new reference rows or a 1.x migration, and for each new 1.x release
(scripts/catch-up-2.0.sh lists it).
"""

import importlib.util
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import init_db
from backend.services import outbound
from backend.services.transaction import recalculate_all_transactions

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "reference_1x.db"
FIGURES = FIXTURES / "reference_1x_figures.json"
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
REMAKE = "rerun backend/tests/fixtures/make_reference_1x_db.py"


def _script(name: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass looks its module up there
    spec.loader.exec_module(module)
    return module


def q(path: Path, sql: str) -> list:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)  # never creates it
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_the_upgraded_1x_ledger_keeps_its_figures(tmp_path, monkeypatch):
    # Price source off, as the figures were made (and test_seed_ledger.py's)
    async def find_prices(day, full):
        return {}, False

    monkeypatch.setattr("backend.services.price_history.find_prices", find_prices)
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings(price_source="off"))
    reference_figures = _script("reference_figures")
    copy = tmp_path / "btctx.db"
    shutil.copyfile(FIXTURE, copy)
    engine = create_engine(f"sqlite:///{copy}", connect_args={"check_same_thread": False})
    init_db(engine)
    with sessionmaker(bind=engine)() as db:
        recalculate_all_transactions(db)
        db.commit()
        now = reference_figures.figures(db)
    engine.dispose()
    # A figure a later version adds isn't in 1.x's file: not a move
    moved = list(reference_figures.differences(json.loads(FIGURES.read_text()), now, allow_new=True))
    assert not moved, "the upgraded 1.x ledger's figures moved:\n" + "\n".join(moved[:20])


def test_the_fixture_holds_no_session_or_ai_key_hash():
    # The repository is public
    kept = q(FIXTURE, "SELECT key, value FROM app_settings WHERE key IN ('open_sessions', 'mcp_key_sha256')")
    assert all(value in ("", None) for _, value in kept), kept


def test_the_fixture_is_the_reference_ledger_s_1x_rows():
    frozen = _script("equivalence_ledgers_1x")
    rows = frozen.reference_rows_1x(SCRIPTS.parent / "testdata" / "reference_ledger.json")
    # Seeded in the file's order, so in id order
    saved = q(FIXTURE, "SELECT type, from_account_id, to_account_id FROM transactions ORDER BY id")
    expected = [(r["type"], r["from_account_id"], r["to_account_id"]) for r in rows]
    assert saved == expected, f"the reference ledger changed: {REMAKE}"
