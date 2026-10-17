"""
Two saves of a setting at the same moment (two tabs or browsers clicking
together) both land, the later one's value kept (#398). A read of the
setting's row, then an insert if it's missing, would let both saves see no
row and fail the second on the key (UNIQUE constraint, a 500), so
models/app_setting.save_setting writes it in one statement.

And two different Privacy & network saves at the same moment leave
BitcoinTX using the later one, what the table holds, never a mix of the two
such as public price sites without Tor (#435): each change commits, then
reads the settings back into memory, one reading at a time
(outbound._one_at_a_time), and they're read in one statement
(outbound._stored), so a commit can't fall between the reads of two of them.
"""

import logging
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


# Two different Privacy & network changes at the same moment (#435): the
# earlier one and the later one, and what the later one leaves in use
TOR = "socks5h://127.0.0.1:9050"
CHANGES_AT_ONCE = {
    # Public price sites through Tor, then Nobody with no proxy: a mix of the
    # two (the issue's) asks public sites directly
    "price choice": (lambda db: outbound.save(db, "public", None, False, TOR),
                     lambda db: outbound.save(db, "off", None, False, None),
                     {"price_source": "off", "proxy_url": None}),
    # Yes, then No, to downloading the price history without Tor (#241)
    "history without Tor": (lambda db: outbound.answer_history_without_tor(db, "yes", "dashboard"),
                            lambda db: outbound.answer_history_without_tor(db, "no", "settings"),
                            {"history_direct": False}),
}


def in_use_is_what_the_table_holds(engine) -> bool:
    """The price settings in memory, and their record, are what the table holds."""
    in_use = (outbound.current(), outbound.as_dict())
    with sessionmaker(bind=engine)() as db:
        outbound.load(db)
    return in_use == (outbound.current(), outbound.as_dict())


class WatchedLock:
    """outbound's lock, setting `held_up` when a thread other than `first`
    finds it held and has to wait for it."""

    def __init__(self, lock, first: threading.Thread, held_up: threading.Event):
        self.lock, self.first, self.held_up = lock, first, held_up

    def __enter__(self):
        if not self.lock.acquire(blocking=False):
            if threading.current_thread() is not self.first:
                self.held_up.set()
            self.lock.acquire()

    def __exit__(self, *exc_info):
        self.lock.release()


@pytest.mark.parametrize("name", CHANGES_AT_ONCE)
def test_a_save_made_while_another_is_read_back_is_the_one_in_use(fresh_db, monkeypatch, name):
    """
    The issue's probe: the earlier save has committed and is reading the
    settings back into memory when the later one, from another tab, saves.
    The later one waits for that reading to end, so it's the one in use,
    neither a mix of the two nor the earlier one read back last.
    """
    earlier, later, expected = CHANGES_AT_ONCE[name]
    first = threading.current_thread()
    later_waits = threading.Event()  # set once the later save is held up by the lock (or is done)
    errors: list[Exception] = []

    def save_later():
        try:
            with sessionmaker(bind=fresh_db)() as db:
                later(db)
        except Exception as e:
            errors.append(e)
        finally:
            later_waits.set()

    later_save = threading.Thread(target=save_later)
    real_server_tor = outbound.server_tor

    def while_reading_back():
        # Read by load() between reading the table and keeping what it read
        if threading.current_thread() is first and later_save.ident is None:
            later_save.start()
            assert later_waits.wait(timeout=10), "the later save never got going"
        return real_server_tor()

    monkeypatch.setattr(outbound, "_one_at_a_time", WatchedLock(outbound._one_at_a_time, first, later_waits))
    monkeypatch.setattr(outbound, "server_tor", while_reading_back)
    with sessionmaker(bind=fresh_db)() as db:
        earlier(db)
    later_save.join(timeout=30)
    assert not later_save.is_alive(), "the later save never finished"
    assert errors == []
    assert {key: getattr(outbound.current(), key) for key in expected} == expected
    assert in_use_is_what_the_table_holds(fresh_db)


def committing_while_reading(engine, key: str, commit):
    """Run commit() once, from the moment a statement reading `key` from
    app_settings is about to run; the listener, to remove."""
    done = threading.Event()

    def at_the_read(conn, cursor, statement, params, context, executemany):
        if not done.is_set() and statement.startswith("SELECT") and "app_settings" in statement and key in params:
            done.set()
            commit()

    event.listen(engine, "before_cursor_execute", at_the_read)
    return at_the_read


NOBODY, PUBLIC_THROUGH_TOR = ("off", None, False, None), ("public", None, False, TOR)


@pytest.mark.parametrize("earlier, later, key", [
    # The save lands as the source is read: read last, it was the later save's
    (NOBODY, PUBLIC_THROUGH_TOR, outbound.SOURCE_KEY),
    # ... or as the proxy is read: read after the source, it was the later save's
    (PUBLIC_THROUGH_TOR, NOBODY, outbound.PROXY_KEY),
], ids=["at the source", "at the proxy"])
def test_a_restore_keeps_one_saves_price_settings(fresh_db, earlier, later, key):
    """
    A restore keeps this install's price settings (outbound.snapshot) and
    writes them into the restored database. A save committing while it
    reads them: what it keeps is one save's, the table's, never one save's
    source with the other's proxy (either way round, public sites with no
    proxy).
    """
    Session = sessionmaker(bind=fresh_db)
    with Session() as db:
        outbound.save(db, *earlier)

    def save_later():
        with Session() as other_tab:
            outbound.save(other_tab, *later)

    listener = committing_while_reading(fresh_db, key, save_later)
    try:
        with Session() as db:
            kept = outbound.snapshot(db)
    finally:
        event.remove(fresh_db, "before_cursor_execute", listener)
    with Session() as db:
        assert kept == outbound.snapshot(db)
    assert (kept[outbound.SOURCE_KEY], kept[outbound.PROXY_KEY]) == (later[0], later[3])


def test_a_change_from_outside_while_the_settings_are_read_leaves_no_mix(fresh_db):
    """
    A change committed by another process (a command, with no part in this
    one's lock) while load() reads the settings: they're read in one
    statement, so what's in use is the table's, before the change or after
    it, never public sites with the proxy the change took away.
    """
    Session = sessionmaker(bind=fresh_db)
    with Session() as db:
        outbound.save(db, "public", None, False, TOR)

    def nobody_from_outside():
        with fresh_db.begin() as other_process:
            other_process.execute(text("UPDATE app_settings SET value = 'off' WHERE key = :k"),
                                  {"k": outbound.SOURCE_KEY})
            other_process.execute(text("DELETE FROM app_settings WHERE key = :k"), {"k": outbound.PROXY_KEY})

    listener = committing_while_reading(fresh_db, outbound.PROXY_KEY, nobody_from_outside)
    try:
        with Session() as db:
            outbound.load(db)
    finally:
        event.remove(fresh_db, "before_cursor_execute", listener)
    assert (outbound.current().price_source, outbound.current().proxy_url) == ("off", None)
    assert in_use_is_what_the_table_holds(fresh_db)


def test_a_reading_back_that_writes_never_waits_for_a_save(fresh_db, monkeypatch, caplog):
    """
    A reading of the settings may write: with the server setting the price
    choice, its note that none was chosen in the app (outbound._mark_unchosen).
    A save meanwhile commits before it waits for its own reading, so it never
    waits holding SQLite's write lock: the note is written, not refused after
    SQLite's 5 seconds while the save waits too.
    """
    monkeypatch.setenv(outbound.ENV_SOURCE, "public")
    first = threading.current_thread()
    held_up = threading.Event()  # set once the save is held up by the lock (or is done)
    errors: list[Exception] = []

    def answer_no():
        try:
            with sessionmaker(bind=fresh_db)() as db:
                outbound.answer_history_without_tor(db, "no", "settings")
        except Exception as e:
            errors.append(e)
        finally:
            held_up.set()

    saving = threading.Thread(target=answer_no)

    def before_the_note(conn, cursor, statement, params, context, executemany):
        if threading.current_thread() is first and statement.startswith("INSERT INTO app_settings") \
                and saving.ident is None:
            saving.start()
            assert held_up.wait(timeout=10), "the save never got going"

    monkeypatch.setattr(outbound, "_one_at_a_time", WatchedLock(outbound._one_at_a_time, first, held_up))
    event.listen(fresh_db, "before_cursor_execute", before_the_note)
    try:
        with sessionmaker(bind=fresh_db)() as db:
            outbound.load(db)  # the server's start
    finally:
        event.remove(fresh_db, "before_cursor_execute", before_the_note)
    saving.join(timeout=30)
    assert not saving.is_alive() and errors == []
    refused = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    assert refused == []  # not "Recording that no price source was chosen in the app failed"
    with fresh_db.connect() as con:
        stored = dict(con.execute(text("SELECT key, value FROM app_settings")).all())
    assert (stored.get(outbound.SOURCE_KEY), stored.get(outbound.DIRECT_KEY)) == ("unset", "no")
    assert in_use_is_what_the_table_holds(fresh_db)
