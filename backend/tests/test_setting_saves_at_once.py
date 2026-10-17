"""
Two saves of a setting at the same moment (two tabs or browsers clicking
together) both land, the later one's value kept (#398). A read of the
setting's row, then an insert if it's missing, would let both saves see no
row and fail the second on the key (UNIQUE constraint, a 500), so
models/app_setting.save_setting writes it in one statement.
"""

import threading

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from backend.models.app_setting import AppSetting, save_setting
from backend.services import ai_key, outbound, tax_time
from backend.tests.conftest import init_test_db, remove_temp_db, temp_db_file


@pytest.fixture
def fresh_db(monkeypatch):
    """A fresh install's database, no setting saved yet; the price
    settings in memory put back afterwards (a save loads its own)."""
    monkeypatch.setattr(outbound, "_current", outbound.NetworkSettings())
    monkeypatch.setattr(outbound, "_record", dict(outbound._record))
    monkeypatch.setattr(outbound, "_direct_record", dict(outbound._direct_record))
    path = temp_db_file()
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    init_test_db(engine)
    yield engine
    engine.dispose()
    remove_temp_db(path)


def save_twice_at_once(engine, save, values) -> list[Exception]:
    """save(db, value) for each value at once, in threads with sessions of
    their own, each reading the settings before either writes; the errors
    raised."""
    both_read = threading.Barrier(len(values), timeout=10)
    waited = threading.local()

    def after_both_read(conn, cursor, statement, params, context, executemany):
        if statement.startswith("INSERT INTO app_settings") and not getattr(waited, "done", False):
            waited.done = True
            both_read.wait()

    errors: list[Exception] = []

    def run(value):
        try:
            with sessionmaker(bind=engine)() as db:
                save(db, value)
        except Exception as e:
            errors.append(e)

    event.listen(engine, "before_cursor_execute", after_both_read)
    try:
        threads = [threading.Thread(target=run, args=(value,)) for value in values]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
    finally:
        event.remove(engine, "before_cursor_execute", after_both_read)
    assert not any(t.is_alive() for t in threads), "a save never finished"
    return errors


def _timezone(db, name):
    tax_time.set_tax_timezone(db, name)
    db.commit()  # as PUT /api/settings/tax-timezone does


SAVES = {
    # Settings -> Privacy & network's Save (PUT /api/settings/network)
    "price choice": (lambda db, v: outbound.save(db, v, None, False, None), outbound.SOURCE_KEY, ["public", "off"]),
    # Download the price history once without Tor? (PUT /api/settings/network/history-without-tor, #396)
    "history without Tor": (lambda db, v: outbound.answer_history_without_tor(db, v, "settings"),
                            outbound.DIRECT_KEY, ["yes", "no"]),
    # Settings -> AI access's switch (PUT /api/settings/ai-access)
    "AI access": (lambda db, v: ai_key.set_access(db, v == "on"), ai_key.ACCESS_KEY, ["on", "off"]),
    # Settings -> Tax timezone (PUT /api/settings/tax-timezone)
    "tax timezone": (_timezone, tax_time.SETTING_KEY, ["America/Chicago", "Asia/Tokyo"]),
}


@pytest.mark.parametrize("name", SAVES)
def test_two_first_saves_at_once_both_land(fresh_db, name):
    save, key, values = SAVES[name]
    assert save_twice_at_once(fresh_db, save, values) == []
    with fresh_db.connect() as con:
        assert con.execute(text("SELECT value FROM app_settings WHERE key = :k"), {"k": key}).scalar() in values


def test_two_first_ai_keys_at_once_leave_one_working(fresh_db):
    """Create key in two tabs: one key's hash is kept, and that key works."""
    tokens = {}

    def create(db, tab):
        tokens[tab] = ai_key.create_key(db)

    assert save_twice_at_once(fresh_db, create, ["tab 1", "tab 2"]) == []
    with sessionmaker(bind=fresh_db)() as db:
        stored = db.get(AppSetting, ai_key.HASH_KEY).value
    assert stored in {ai_key._hash(token) for token in tokens.values()}


def test_a_save_is_read_back_in_the_same_session(fresh_db):
    """A setting read earlier in the session is read again after a save
    (or a deletion), not kept from before it."""
    with sessionmaker(bind=fresh_db)() as db:
        save_setting(db, "k", "old")
        db.commit()
        row = db.get(AppSetting, "k")  # held, so the session keeps it
        assert row.value == "old"
        save_setting(db, "k", "new")
        assert (row.value, db.get(AppSetting, "k").value) == ("new", "new")
        save_setting(db, "k", None)
        assert db.get(AppSetting, "k") is None
        db.commit()
    with fresh_db.connect() as con:
        assert con.execute(text("SELECT count(*) FROM app_settings WHERE key = 'k'")).scalar() == 0
