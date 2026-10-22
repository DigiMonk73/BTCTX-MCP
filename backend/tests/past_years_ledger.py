"""
The reference test ledger (testdata/reference_ledger.json, 2023-2026) put
into a fresh install by scripts/seed_ledger.py, for the past-year warning's
tests (5.8, B6b). It goes in while "this tax year" is still the tests'
2009 (conftest.py), so no row meets the warning on its way in.
"""

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from backend.main import app
from backend.services import first_run

USER, PASSWORD = "past-years-user", "past-years-password-123"


def _seed_ledger():
    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_ledger.py"
    spec = importlib.util.spec_from_file_location("seed_ledger", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed_ledger = _seed_ledger()


def seeded_client() -> TestClient:
    """A logged-in client of the fresh install (conftest's fresh_app) with
    the whole reference ledger in it."""
    c = TestClient(app)
    seed_ledger.log_in(c, USER, PASSWORD, first_run.ensure_code())
    assert seed_ledger.seed(c) == len(seed_ledger.ledger_rows())
    return c


def own_app(tmp_path):
    """The app on a database of its own in tmp_path (its copies go to
    tmp_path/backups): yields (the database's path, its sessionmaker, a
    client logged in as the owner, a client with only an AI key, AI access
    on). For a fixture: `yield from own_app(tmp_path)`."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.database import get_db
    from backend.tests.conftest import default_login, init_test_db

    path = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    Session = sessionmaker(bind=engine)

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides[get_db]
    app.dependency_overrides[get_db] = override
    first_run.clear_code()
    owner = TestClient(app)
    assert owner.post("/api/login", json=default_login()).status_code == 200
    assert owner.put("/api/settings/ai-access", json={"on": True}).status_code == 200
    ai = TestClient(app, headers={"Authorization": f"Bearer {owner.post('/api/settings/ai-key').json()['key']}"})
    yield path, Session, owner, ai
    first_run.clear_code()
    app.dependency_overrides[get_db] = previous
    engine.dispose()
