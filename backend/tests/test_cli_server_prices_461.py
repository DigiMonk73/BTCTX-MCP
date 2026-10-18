"""
#461: on StartOS a maintenance command run by hand (`python -m backend.cli
review`, `recalculate`) may lack the server's price variables, which the
app itself runs with. It then asked by the app's stored choice: public
sites without the server's Tor (BTCTX_TOR_PROXY_URL), or despite the
action's Nobody (BTCTX_PRICE_SOURCE) over a choice once made in the app.

The owner's design, "Ask no one" (2026-10-17, on #461): the app's start
notes which of the server's price settings it has, and a command lacking
them asks no one and says so on stderr. With them it asks as it did. The
outside sites are faked; each request carries the proxy it took
(outbound.PROXY_TAG).
"""

import sqlite3

import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import backend.database as database
from backend import cli
from backend.database import init_db
from backend.services import outbound, price_history
from backend.services import hourly_prices as hp
from backend.tests.conftest import default_login, keep_in_use

# The real function, captured before the session fixture stubs it.
from backend.services.price_history import find_prices as real_find_prices

TOR = "socks5h://127.0.0.1:9050"
SERVER_VARIABLES = (outbound.ENV_SOURCE, outbound.ENV_FALLBACK, outbound.ENV_MEMPOOL, outbound.ENV_PROXY,
                    outbound.ENV_TOR)
# A choice made in the app before the action took over: public sites, confirmed, no proxy of its own
APP_CHOICE = {"price_source": "public", "mempool_fallback": "off",
              "price_choice_at": "2026-10-01T12:00:00Z", "price_choice_via": "settings"}


@pytest.fixture
def server(tmp_path, monkeypatch):
    """A database of its own with the app's choice above and a gift whose
    value is blank (Ledger Review prices it), the real daily price lookups
    against fake sites that record each request with its proxy, and none of
    the server's variables set. Yields the requests seen."""
    for name in SERVER_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "btctx.db"
    engine = create_engine(f"sqlite:///{path}")
    init_db(engine)
    with sqlite3.connect(path) as con:
        con.executemany("INSERT INTO app_settings (key, value) VALUES (?, ?)", APP_CHOICE.items())
        # Before the hourly year files (2013): the day's price, from Bitstamp's daily history
        con.execute("INSERT INTO transactions (id, type, timestamp, from_account_id, to_account_id, amount,"
                    " fee_amount, fee_currency, purpose) VALUES"
                    " (1, 'Withdrawal', '2012-05-17 12:00:00', 2, 99, '0.1', '0', 'BTC', 'Gift')")
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(database, "init_db", lambda: init_db(engine))
    seen: list[tuple[str, str | None]] = []

    def sites(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.extensions.get(outbound.PROXY_TAG, "untagged")))
        return httpx.Response(503)

    monkeypatch.setattr(outbound, "_transport", httpx.MockTransport(sites))
    monkeypatch.setattr(price_history, "find_prices", real_find_prices)
    for name in ("_current", "_record", "_direct_record"):  # put back after the test
        value = getattr(outbound, name)
        monkeypatch.setattr(outbound, name, dict(value) if isinstance(value, dict) else value)
    price_history.reset_state()
    hp.reset_state()
    yield seen
    price_history.reset_state()
    hp.reset_state()


def app_starts(monkeypatch, **variables):
    """The app's start with these of the server's variables (main.py reads the settings so)."""
    for name in SERVER_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    with database.SessionLocal() as db:
        outbound.load(db)


def run_by_hand(monkeypatch, capsys, *args, **variables):
    """The command, run with only these of the server's variables: its
    stderr (each line), after checking it succeeded."""
    for name in SERVER_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    for name, value in variables.items():
        monkeypatch.setenv(name, value)
    capsys.readouterr()
    assert cli.main(list(args)) == 0
    return capsys.readouterr().err


def noted() -> str | None:
    with database.SessionLocal() as db:
        return outbound._get(db, outbound.SERVER_SET_KEY)


def test_without_the_servers_tor_a_command_asks_no_one(server, monkeypatch, capsys):
    """The issue's probe: Decide in BitcoinTX instead with Use Tor. The
    stored choice is public with no proxy of the owner's, and the command
    went to Bitstamp directly, around Tor."""
    app_starts(monkeypatch, BTCTX_TOR_PROXY_URL=TOR)
    err = run_by_hand(monkeypatch, capsys, "review")
    assert server == []
    assert "note: BitcoinTX last started with the server's price settings (BTCTX_TOR_PROXY_URL)" in err
    assert "so it asks no one for a price" in err
    assert not outbound.current().public_allowed and outbound.current().own_node is None


@pytest.mark.parametrize("variables", [{}, {outbound.ENV_TOR: TOR}], ids=["none", "only-tor"])
def test_without_the_servers_choice_a_command_asks_no_one(server, monkeypatch, capsys, variables):
    """The action's Nobody over the public choice once made in the app: the
    stored choice stays underneath, and the command asked public sites. The
    server's Tor alone doesn't stand for its choice."""
    app_starts(monkeypatch, BTCTX_PRICE_SOURCE="off")
    err = run_by_hand(monkeypatch, capsys, "review", **variables)
    assert server == []
    assert "server's price settings (BTCTX_PRICE_SOURCE)" in err


def test_recalculate_says_so_too(server, monkeypatch, capsys):
    with database.SessionLocal() as db:  # a gift with nothing to give: no ledger to rebuild
        db.execute(text("DELETE FROM transactions"))
        db.commit()
    app_starts(monkeypatch, BTCTX_PRICE_SOURCE="public", BTCTX_PROXY_URL=TOR)
    err = run_by_hand(monkeypatch, capsys, "recalculate")
    assert "so it asks no one for a price" in err
    assert not outbound.current().asking


@pytest.mark.parametrize("variables", [
    {outbound.ENV_TOR: TOR},  # Decide in BitcoinTX instead, with Use Tor
    {outbound.ENV_SOURCE: "public", outbound.ENV_FALLBACK: "off", outbound.ENV_PROXY: TOR},  # the action's choice
], ids=["servers-tor", "servers-choice"])
def test_with_the_variables_a_command_asks_as_the_app_does(server, monkeypatch, capsys, variables):
    """The package's own runs (Recalculate Ledger, the migrate oneshot) pass
    them, as Docker's `docker exec` does: the same requests as before, through Tor."""
    app_starts(monkeypatch, **variables)
    err = run_by_hand(monkeypatch, capsys, "review", **variables)
    assert server and {proxy for _, proxy in server} == {TOR}
    assert {host for host, _ in server} <= {"www.bitstamp.net", "api.kraken.com"}
    assert "asks no one" not in err


def test_a_start_without_the_variables_takes_the_note_away(server, monkeypatch, capsys):
    """A Docker or source install that stops setting them, or StartOS back
    to Decide in BitcoinTX instead without Tor: the stored choice is the one
    in use again, for the app and a command alike."""
    app_starts(monkeypatch, BTCTX_TOR_PROXY_URL=TOR)
    assert noted() == "tor"
    app_starts(monkeypatch)
    assert noted() is None
    err = run_by_hand(monkeypatch, capsys, "review")
    assert server and {proxy for _, proxy in server} == {None}  # the stored choice: public, no proxy
    assert err == ""


def test_the_note_follows_the_variables_the_app_starts_with(server, monkeypatch):
    app_starts(monkeypatch)
    assert noted() is None  # the Mac app, and any install without them: nothing written
    app_starts(monkeypatch, BTCTX_TOR_PROXY_URL=TOR)
    assert noted() == "tor"
    app_starts(monkeypatch, BTCTX_PRICE_SOURCE="mempool", BTCTX_TOR_PROXY_URL=TOR)
    assert noted() == "source"
    app_starts(monkeypatch, BTCTX_PRICE_SOURCE="nonsense")  # invalid: the server's all the same
    assert noted() == "source"


def test_a_command_never_writes_the_note(server, monkeypatch, capsys):
    """Like the price choice (#134): only the app's start says what the server gives it."""
    run_by_hand(monkeypatch, capsys, "review", BTCTX_TOR_PROXY_URL=TOR)
    assert noted() is None
    app_starts(monkeypatch, BTCTX_TOR_PROXY_URL=TOR)
    run_by_hand(monkeypatch, capsys, "migrate", BTCTX_PRICE_SOURCE="public")
    run_by_hand(monkeypatch, capsys, "review")
    assert noted() == "tor"


def test_only_commands_that_may_look_up_a_price_say_so(server, monkeypatch, capsys):
    """Set Login Credentials and migrate never look one up: no note on their stderr."""
    app_starts(monkeypatch, BTCTX_TOR_PROXY_URL=TOR)
    assert run_by_hand(monkeypatch, capsys, "migrate") == ""
    assert not outbound.current().asking


def test_a_restore_keeps_this_installs_note(auth_client, test_engine, monkeypatch):
    """An in-app restore keeps this install's price settings, not a backup's
    (#201): the note too, and the restore's read-back check passes with it."""
    from backend.routers import backup

    for name in SERVER_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(outbound.ENV_TOR, TOR)
    with sessionmaker(bind=test_engine)() as db:
        outbound.load(db)
    seen_in_restore = []

    def restore_old_backup(password, path, carry_over):  # a backup with no note
        with test_engine.begin() as conn:
            conn.exec_driver_sql("DELETE FROM app_settings WHERE key = ?", (outbound.SERVER_SET_KEY,))
        keep_in_use(test_engine, carry_over)
        with test_engine.connect() as conn:
            seen_in_restore.append(conn.exec_driver_sql(
                "SELECT value FROM app_settings WHERE key = ?", (outbound.SERVER_SET_KEY,)).scalar())

    monkeypatch.setattr(backup, "restore_backup", restore_old_backup)
    try:
        r = auth_client.post("/api/backup/restore", data={"password": "pw"}, files={"file": ("b.btx", b"x")})
        assert r.status_code == 200, r.text
        assert seen_in_restore == ["tor"]
    finally:
        monkeypatch.delenv(outbound.ENV_TOR)
        with sessionmaker(bind=test_engine)() as db:
            outbound.load(db)  # the test database's own start again: no note
        # The restoring browser logs in again; the shared client stays logged in for the next tests
        assert auth_client.post("/api/login", json=default_login()).status_code == 200
