"""
backend/tests/test_migrations.py

Schema migrations (backend/migrate.py, backend/migrations/):
  - the migrations and the models describe the same schema (drift guard:
    changing a model without writing a migration fails here)
  - a real database written by v0.7.0 (fixtures/v0_7_0.db) is backed up,
    adopted, upgraded, and the app then works on it
  - older installs (no FK indexes, missing columns) are repaired on adoption
  - failures roll back completely; unknown/newer schemas are refused
  - restoring an old encrypted backup upgrades it before it replaces the live DB
"""

from backend.tests.conftest import default_login
import shutil
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import backend.migrate as migrate
from backend.database import Base, get_db, init_db
from backend.main import app
from backend.migrate import MigrationError, head_revision, upgrade_database
from backend.services.backup import make_backup, restore_backup

FIXTURE = Path(__file__).parent / "fixtures" / "v0_7_0.db"
FK_INDEXES = [
    "ix_ledger_entries_transaction_id", "ix_ledger_entries_account_id",
    "ix_bitcoin_lots_created_txn_id", "ix_lot_disposals_lot_id", "ix_lot_disposals_transaction_id",
]


def engine_for(path: Path):
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def q(path: Path, sql: str):
    con = sqlite3.connect(str(path))
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def schema(path: Path) -> dict:
    return {
        name: " ".join(sql.split())
        for name, sql in q(path, "SELECT name, sql FROM sqlite_master WHERE sql IS NOT NULL")
        if name != "alembic_version"
    }


@pytest.fixture
def v070(tmp_path) -> Path:
    db = tmp_path / "btctx.db"
    shutil.copy(FIXTURE, db)
    return db


# ---------------------------------------------------------------------------
# Migrations vs models
# ---------------------------------------------------------------------------
def test_models_and_migrations_agree(tmp_path):
    """If this fails you changed a model without a migration (or vice versa).
    Write one: see docs/MAINTENANCE.md, "Database migrations"."""
    migrated, created = tmp_path / "migrated.db", tmp_path / "created.db"
    upgrade_database(engine_for(migrated))
    Base.metadata.create_all(engine_for(created))

    with engine_for(migrated).connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)
    assert diff == []
    assert schema(migrated) == schema(created)


def test_fresh_database_goes_to_head_without_a_backup(tmp_path):
    db = tmp_path / "btctx.db"
    result = init_db(engine_for(db))
    assert (result.from_revision, result.to_revision) == (None, head_revision())
    assert result.backup is None and not (tmp_path / "backups").exists()
    assert q(db, "SELECT username FROM users") == [("admin",)]
    assert [r[0] for r in q(db, "SELECT id FROM accounts ORDER BY id")] == [1, 2, 3, 4, 5, 6]


def test_second_start_changes_nothing(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    result = init_db(engine_for(db))
    assert not result.changed and result.backup is None


# ---------------------------------------------------------------------------
# Adopting databases from before migrations
# ---------------------------------------------------------------------------
def old_columns(table: str) -> str:
    """The fixture's columns that are still there at head (0005 drops is_locked)."""
    return ", ".join(row[1] for row in q(FIXTURE, f"PRAGMA table_info({table})") if row[1] != "is_locked")


def test_v0_7_0_database_is_backed_up_adopted_and_usable(v070):
    cols = old_columns("transactions")
    before = q(v070, f"SELECT {cols} FROM transactions ORDER BY id")
    result = init_db(engine_for(v070))

    assert result.adopted and result.repairs == []
    assert q(v070, "SELECT version_num FROM alembic_version") == [(head_revision(),)]
    assert q(v070, f"SELECT {cols} FROM transactions ORDER BY id") == before
    assert q(v070, "SELECT DISTINCT broker_reporting FROM transactions") == [(None,)]  # 0003
    # the backup is the untouched v0.7.0 file
    assert result.backup.parent == v070.parent / "backups"
    assert oct(result.backup.stat().st_mode & 0o777) == "0o600"
    assert schema(result.backup) == schema(FIXTURE)

    # the current app works on it
    Session = sessionmaker(bind=engine_for(v070))

    def override():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override
    try:
        client = TestClient(app)
        assert client.post("/api/login", json=default_login()).status_code == 200
        assert len(client.get("/api/transactions").json()) == 7
        assert client.post("/api/transactions/recalculate").status_code == 200
        assert client.put("/api/settings/tax-timezone", json={"timezone": "America/Chicago", "chosen": True}).status_code == 200
        pdf = client.get("/api/reports/irs_reports", params={"year": 2024})
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous


def test_0004_stores_each_transfer_fee_at_the_value_it_already_had(v070):
    """Upgrading changes no figure: a transfer's BTC fee gets the USD value
    its fee disposal already carries, and recalculation reuses it."""
    disposals = "SELECT SUM(proceeds_usd_for_that_portion) FROM lot_disposals d " \
                "JOIN transactions t ON t.id = d.transaction_id WHERE t.type = 'Transfer'"
    (before,), = q(v070, disposals)
    # Make the stored value differ from any price the tests stub, so a
    # re-priced fee would show.
    con = sqlite3.connect(str(v070))
    con.execute("UPDATE lot_disposals SET proceeds_usd_for_that_portion = '4.21' WHERE transaction_id ="
                " (SELECT id FROM transactions WHERE type = 'Transfer')")
    con.commit()
    con.close()
    init_db(engine_for(v070))
    assert q(v070, "SELECT fee_usd, fee_usd_manual FROM transactions WHERE type = 'Transfer'") == [(4.21, 0)]
    assert q(v070, "SELECT COUNT(*) FROM transactions WHERE type != 'Transfer' AND fee_usd IS NOT NULL") == [(0,)]
    assert before is not None

    from backend.services.transaction import recalculate_all_transactions

    with sessionmaker(bind=engine_for(v070))() as db:
        recalculate_all_transactions(db)
        db.commit()
    assert q(v070, disposals) == [(4.21,)]


@pytest.mark.parametrize("sqlite_version", [None, (3, 34, 0)], ids=["in place", "rebuilt"])
def test_0005_drops_the_lock_column_and_keeps_every_row(v070, monkeypatch, sqlite_version):
    """The lock column goes and every other value stays, whether SQLite drops
    the column in place (3.35+) or the table is rebuilt (older SQLite)."""
    engine = engine_for(v070)
    if sqlite_version:
        monkeypatch.setattr(engine.dialect.dbapi, "sqlite_version_info", sqlite_version)
    tables = ("transactions", "ledger_entries", "bitcoin_lots", "lot_disposals")
    before = {t: q(v070, f"SELECT {old_columns(t)} FROM {t} ORDER BY id") for t in tables}
    assert all(before.values())

    init_db(engine)

    assert "is_locked" not in [row[1] for row in q(v070, "PRAGMA table_info(transactions)")]
    assert {t: q(v070, f"SELECT {old_columns(t)} FROM {t} ORDER BY id") for t in tables} == before
    rebuilt = q(v070, "SELECT sql FROM sqlite_master WHERE name = 'transactions'")[0][0].startswith(
        'CREATE TABLE "transactions"')
    assert rebuilt == bool(sqlite_version)
    with engine.connect() as conn:
        assert compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata) == []


def test_pre_2026_database_gets_its_missing_indexes(v070):
    con = sqlite3.connect(str(v070))
    for name in FK_INDEXES:  # added to the models in Jan 2026 (v0.5.x DBs lack them)
        con.execute(f"DROP INDEX {name}")
    con.commit()
    con.close()

    result = init_db(engine_for(v070))
    assert sorted(result.repairs) == sorted(f"created index {n}" for n in FK_INDEXES)
    after, original = schema(v070), schema(FIXTURE)
    assert {n: after[n] for n in FK_INDEXES} == {n: original[n] for n in FK_INDEXES}


def test_missing_nullable_columns_are_added_and_data_kept(v070):
    con = sqlite3.connect(str(v070))
    con.execute("ALTER TABLE transactions DROP COLUMN fmv_usd")
    con.execute("ALTER TABLE transactions DROP COLUMN gross_proceeds_usd")
    con.commit()
    con.close()
    ids = q(v070, "SELECT id, type, amount FROM transactions ORDER BY id")

    result = init_db(engine_for(v070))
    assert set(result.repairs) == {
        "added column transactions.gross_proceeds_usd", "added column transactions.fmv_usd",
    }
    assert q(v070, "SELECT id, type, amount FROM transactions ORDER BY id") == ids


def test_dev_build_database_with_app_settings_keeps_its_settings(v070):
    con = sqlite3.connect(str(v070))
    con.execute("CREATE TABLE app_settings (key VARCHAR NOT NULL, value VARCHAR NOT NULL, PRIMARY KEY (key))")
    con.execute("INSERT INTO app_settings VALUES ('tax_timezone', 'America/Denver')")
    con.commit()
    con.close()

    init_db(engine_for(v070))
    assert q(v070, "SELECT value FROM app_settings WHERE key = 'tax_timezone'") == [("America/Denver",)]


def test_foreign_database_is_refused(tmp_path):
    db = tmp_path / "other.db"
    q(db, "CREATE TABLE notes (id INTEGER)")
    with pytest.raises(MigrationError, match="isn't a BitcoinTX database"):
        upgrade_database(engine_for(db))
    assert q(db, "SELECT name FROM sqlite_master WHERE type='table'") == [("notes",)]


def test_newer_schema_is_refused(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.execute("UPDATE alembic_version SET version_num = 'ffff'")
    con.commit()
    con.close()
    with pytest.raises(MigrationError, match="newer version"):
        upgrade_database(engine_for(db))


def test_failed_upgrade_rolls_back_completely(v070, monkeypatch):
    real_upgrade = migrate.command.upgrade

    def upgrade_then_fail(cfg, target):
        real_upgrade(cfg, target)
        if target == "head":  # the real upgrade, after adoption's repairs + stamp
            raise RuntimeError("disk on fire")

    con = sqlite3.connect(str(v070))
    con.execute(f"DROP INDEX {FK_INDEXES[0]}")
    con.commit()
    con.close()
    before = schema(v070)

    monkeypatch.setattr(migrate.command, "upgrade", upgrade_then_fail)
    with pytest.raises(MigrationError, match="disk on fire") as err:
        upgrade_database(engine_for(v070))

    # adoption stamp, index repair and the app_settings table are all gone
    assert schema(v070) == before
    assert not q(v070, "SELECT name FROM sqlite_master WHERE name = 'alembic_version'")
    # and so is the pre-2.0 copy, which nothing prunes: each failed start (a
    # restart loop) would add one
    assert "Your database is unchanged." in str(err.value)
    assert migrate.backup_copies(v070, "pre-2.0") == []


# ---------------------------------------------------------------------------
# Restoring encrypted backups
# ---------------------------------------------------------------------------
@pytest.fixture
def live(tmp_path):
    """A current, migrated live database with one user renamed so we can
    tell it apart from a restored one."""
    db = tmp_path / "live" / "btctx.db"
    db.parent.mkdir()
    engine = engine_for(db)
    init_db(engine)
    q_con = sqlite3.connect(str(db))
    q_con.execute("UPDATE users SET username = 'live-user'")
    q_con.commit()
    q_con.close()
    return db, engine


def test_restoring_a_v0_7_0_backup_upgrades_it(tmp_path, live):
    db, engine = live
    btx = tmp_path / "old.btx"
    make_backup("pw", btx, db_path=FIXTURE)

    result = restore_backup("pw", btx, db_path=db, engine=engine)

    assert result.adopted and result.to_revision == head_revision()
    assert q(db, "SELECT version_num FROM alembic_version") == [(head_revision(),)]
    assert q(db, "SELECT count(*) FROM transactions") == [(7,)]
    kept = list((db.parent / "backups").glob("btctx-before-restore-*.db"))
    assert len(kept) == 1 and q(kept[0], "SELECT username FROM users") == [("live-user",)]
    assert not (db.parent / "btctx.db.restoring").exists()


@pytest.mark.parametrize("case", ["wrong-password", "not-a-database", "newer-schema"])
def test_bad_restore_leaves_the_live_database_alone(tmp_path, live, case):
    db, engine = live
    before = q(db, "SELECT username FROM users")
    btx = tmp_path / "x.btx"
    if case == "not-a-database":
        junk = tmp_path / "junk.db"
        junk.write_bytes(b"hello" * 100)
        from backend.services import backup as svc
        salt, iv = b"s" * svc.SALT_LENGTH, b"i" * svc.IV_LENGTH
        btx.write_bytes(salt + iv + svc._encrypt_data(junk.read_bytes(), svc._derive_key("pw", salt), iv))
    else:
        newer = tmp_path / "newer.db"
        init_db(engine_for(newer))
        if case == "newer-schema":
            con = sqlite3.connect(str(newer))
            con.execute("UPDATE alembic_version SET version_num = 'ffff'")
            con.commit()
            con.close()
        make_backup("pw", btx, db_path=newer)

    with pytest.raises(ValueError):
        restore_backup("wrong" if case == "wrong-password" else "pw", btx, db_path=db, engine=engine)
    assert q(db, "SELECT username FROM users") == before
    assert not (db.parent / "btctx.db.restoring").exists()
    assert not (db.parent / "backups").exists()


# ---------------------------------------------------------------------------
# 2.0's first migration (0100): exchanges, kinds and names (2.0 spec 5.2, 5.3)
# ---------------------------------------------------------------------------
OLD_ACCOUNTS = Path(__file__).parent / "fixtures" / "old_accounts_1x.db"
REFERENCE_1X = Path(__file__).parent / "fixtures" / "reference_1x.db"
FIGURE_TABLES = ("transactions", "ledger_entries", "bitcoin_lots", "lot_disposals")
ACCOUNT_ROWS = "SELECT id, name, currency, kind, exchange_id, hidden FROM accounts ORDER BY id"
FIXED_ROWS = [
    (1, "Bank", "USD", "bank", None, 0), (2, "Wallet", "BTC", "wallet", None, 0),
    (3, "Exchange USD", "USD", "exchange", 1, 0), (4, "Exchange BTC", "BTC", "exchange", 1, 0),
    (5, "BTC Fees", "BTC", "fee", None, 0), (6, "USD Fees", "USD", "fee", None, 0),
]


def _move_to(path: Path, revision: str, how=command.upgrade) -> None:
    """The database up (or down) to one revision, as Alembic runs it."""
    engine = engine_for(path)
    with engine.begin() as conn:
        if how is command.upgrade and migrate.current_revision(conn) is None and migrate._app_tables(conn):
            migrate.adopt_unversioned(conn)
        cfg = migrate.alembic_config()
        cfg.attributes["connection"] = conn
        how(cfg, revision)
    engine.dispose()


def _copy(source: Path, tmp_path: Path, name="btctx.db") -> Path:
    db = tmp_path / name
    shutil.copy(source, db)
    return db


def _ours():
    return migrate._script().get_revision(migrate.first_2_0()).module


def test_exactly_one_migration_starts_2_0_and_1x_is_one_chain_below_it():
    script = migrate._script()
    marked = [r.revision for r in script.walk_revisions() if getattr(r.module, "STARTS_2_0", False)]
    assert marked == [migrate.first_2_0()] == ["0100"]
    first = script.get_revision(migrate.first_2_0())
    below = {r.revision for r in script.iterate_revisions(first.down_revision, "base")}
    everything = {r.revision for r in script.walk_revisions()}
    assert everything - migrate.revisions_of_2_0() == below
    assert all(revision < "0100" for revision in below)
    assert all(revision >= "0100" for revision in migrate.revisions_of_2_0())


def test_the_migration_writes_no_exchange_into_a_fresh_database(tmp_path):
    """A restore copies a backup's rows into a database its migrations made:
    a row of the migration's own would clash with the backup's."""
    db = tmp_path / "btctx.db"
    upgrade_database(engine_for(db), backup=False)
    assert q(db, "SELECT count(*) FROM exchanges") == [(0,)]
    init_db(engine_for(db))
    assert q(db, "SELECT id, name, sends_1099da FROM exchanges") == [(1, "Exchange", 1)]
    assert q(db, ACCOUNT_ROWS) == FIXED_ROWS


@pytest.mark.parametrize("fixture", [FIXTURE, REFERENCE_1X, OLD_ACCOUNTS], ids=["v0.7.0", "reference 1.x", "old accounts"])
def test_the_migration_moves_no_stored_figure(tmp_path, fixture):
    at_1x, at_2_0 = _copy(fixture, tmp_path, "1x.db"), _copy(fixture, tmp_path, "2.0.db")
    _move_to(at_1x, "0012")
    _move_to(at_2_0, "head")
    for table in FIGURE_TABLES:
        # 1.x's columns as they were; a column 2.0 adds (0101's) holds nothing yet
        columns = [row[1] for row in q(at_1x, f"PRAGMA table_info({table})")]
        added = [row[1] for row in q(at_2_0, f"PRAGMA table_info({table})") if row[1] not in columns]
        select = f"SELECT {', '.join(columns)} FROM {table} ORDER BY id"
        assert q(at_2_0, select) == q(at_1x, select)
        for column in added:
            assert q(at_2_0, f"SELECT count(*) FROM {table} WHERE {column} IS NOT NULL") == [(0,)]
    assert q(at_2_0, "SELECT count(*) FROM chosen_coins") == [(0,)]
    assert q(at_2_0, "SELECT version_num FROM alembic_version") == [(head_revision(),)]


def test_a_1x_ledger_gets_its_kinds_and_exchange_1(v070):
    init_db(engine_for(v070))
    assert q(v070, ACCOUNT_ROWS) == FIXED_ROWS
    assert q(v070, "SELECT id, name, sends_1099da FROM exchanges") == [(1, "Exchange", 1)]


def test_an_old_ledgers_accounts_are_taken_in(tmp_path):
    """5.15's old database: "cold2" (7) a wallet; "wallet" (8), alike the
    reserved "Wallet", a bank renamed; #289's second "BTC Fees" (9), which
    1.x's engine made and put a fee's lines in, a fee account renamed, so 5
    takes its 1.x name back and the app starts; the row naming 999 left as
    it is."""
    db = _copy(OLD_ACCOUNTS, tmp_path)
    columns = ", ".join(row[1] for row in q(db, "PRAGMA table_info(transactions)"))  # 1.x's
    naming_999 = q(db, f"SELECT {columns} FROM transactions WHERE to_account_id = 999")
    assert q(db, "SELECT count(*) FROM ledger_entries WHERE account_id = 9") == [(1,)]
    init_db(engine_for(db))
    assert q(db, ACCOUNT_ROWS) == FIXED_ROWS + [
        (7, "cold2", "BTC", "wallet", None, 0),
        (8, "wallet (account 8)", "USD", "bank", None, 0),
        (9, "BTC Fees (account 9)", "BTC", "fee", None, 0),
    ]
    assert q(db, f"SELECT {columns} FROM transactions WHERE to_account_id = 999") == naming_999


def test_an_account_with_externals_id_is_a_fee_account(v070):
    """External is 99 everywhere (5.4): a row of that id, possible only after
    93 accounts made through 1.x's API, is internal, never one of yours."""
    con = sqlite3.connect(str(v070))
    con.execute("INSERT INTO accounts (id, user_id, name, currency) VALUES (99, 1, 'Somewhere', 'BTC')")
    con.commit()
    con.close()
    init_db(engine_for(v070))
    assert q(v070, "SELECT kind FROM accounts WHERE id = 99") == [("fee",)]


@pytest.mark.parametrize("rows, names", [
    ([(7, " Cold\u200b  Storage\t")], {7: "Cold Storage"}),  # a format and a control character, runs of spaces
    ([(7, "\u202eevil\u2066")], {7: "evil"}),  # bidirectional controls
    ([(7, "a\u200db")], {7: "a\u200db"}),  # the zero-width joiner stays
    ([(7, "Cafe\u0301")], {7: "Caf\u00e9"}),  # NFC
    ([(12, "  \u200b ")], {12: "account 12"}),
    ([(7, "x" * 50)], {7: "x" * 40}),
    ([(10, "Cold"), (11, "COLD")], {10: "Cold", 11: "COLD (account 11)"}),
    ([(11, "COLD"), (10, "Cold")], {10: "Cold", 11: "COLD (account 11)"}),  # the lower id keeps it
    ([(12, "external")], {12: "external (account 12)"}),
    ([(12, "Exchange BTC")], {12: "Exchange BTC (account 12)"}),
    ([(13, "y" * 45), (14, "Y" * 41)], {13: "y" * 40, 14: "Y" * 27 + " (account 14)"}),
    ([(13, "mine"), (14, "Mine (account 15)"), (15, "MINE")],
     {13: "mine", 14: "Mine (account 15)", 15: "MINE (account 15, 2)"}),
    ([(16, "Cafe\u0301"), (17, "CAF\u00c9")], {16: "Caf\u00e9", 17: "CAF\u00c9 (account 17)"}),
    ([(7, "x" * 39 + " yz")], {7: "x" * 39}),  # no space left at the cut
    ([(7, "Wallet\u200d")], {7: "Wallet (account 7)"}),  # a joiner at the end goes
    ([(7, "Wallet\u034f")], {7: "Wallet (account 7)"}),  # so does what nothing shows
    ([(7, "Cold \u2744\ufe0f")], {7: "Cold \u2744\ufe0f"}),  # but an emoji keeps its variation selector
    ([(7, "Co\u034fld"), (8, "cold")], {7: "Co\u034fld", 8: "cold (account 8)"}),  # alike: it's left out
    ([(7, "a\u200db"), (8, "ab")], {7: "a\u200db", 8: "ab (account 8)"}),  # alike: joiners ignored
    ([(7, "x" * 39 + "\u200dy")], {7: "x" * 39}),  # nor a joiner
    ([(7, "'=Cold")], {7: "'=Cold"}),  # an apostrophe stays: 2.0's names' rule decides (B2b)
    ([(7, "\u200d \u200c")], {7: "account 7"}),
])
def test_the_migration_cleans_and_frees_each_extra_accounts_name(rows, names):
    fixed = [(i, name) for i, name, *_ in FIXED_ROWS]
    assert _ours().free_names(fixed + rows) == {**dict(fixed), **names}


@pytest.mark.parametrize("rows, names", [
    # #289: 5 renamed beside a second "BTC Fees", which a 1.x start couldn't fix
    ([(1, "Bank"), (5, "Fees"), (9, "BTC Fees"), (10, "fees")],
     {1: "Bank", 5: "BTC Fees", 9: "BTC Fees (account 9)", 10: "fees"}),
    # 5 renamed alike 6's name: the rebuild's unique name would have failed
    ([(5, "usd fees"), (6, "USD Fees")], {5: "BTC Fees", 6: "USD Fees"}),
])
def test_ids_1_to_6_take_their_1x_names(rows, names):
    """Every 1.x start gave them those names; only a ledger #289 stopped
    starting holds another."""
    assert _ours().free_names(rows) == names


def test_the_migration_goes_back_to_0012(tmp_path):
    db = _copy(OLD_ACCOUNTS, tmp_path)
    init_db(engine_for(db))
    _move_to(db, "0012", how=command.downgrade)
    at_0012 = tmp_path / "0012.db"
    _move_to(at_0012, "0012")
    assert schema(db) == schema(at_0012)
    assert q(db, "SELECT id, name, currency FROM accounts WHERE id IN (8, 9) ORDER BY id") == [
        (8, "wallet (account 8)", "USD"), (9, "BTC Fees (account 9)", "BTC")]


# The seed (2.0 spec 5.2): ids 1-4 keep the names the owner gave them; 5 and
# 6 get theirs back; each gets back its currency, kind and exchange
def test_the_seed_keeps_1_to_4s_names_and_puts_back_the_rest(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.executescript("""
        UPDATE accounts SET name = 'Checking', kind = 'wallet' WHERE id = 1;
        UPDATE accounts SET name = 'Cold', currency = 'USD' WHERE id = 2;
        UPDATE accounts SET exchange_id = NULL, kind = 'bank' WHERE id = 3;
        UPDATE accounts SET name = 'Fees' WHERE id = 5;
        UPDATE accounts SET name = 'Dollar fees', kind = 'bank' WHERE id = 6;
    """)
    con.close()
    init_db(engine_for(db))
    assert q(db, ACCOUNT_ROWS) == [(1, "Checking", "USD", "bank", None, 0), (2, "Cold", "BTC", "wallet", None, 0),
                                   *FIXED_ROWS[2:]]


def test_the_seed_makes_a_missing_exchange_account_from_its_exchanges_name(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.executescript("UPDATE exchanges SET name = 'River'; DELETE FROM accounts WHERE id IN (3, 4);")
    con.close()
    init_db(engine_for(db))
    assert q(db, ACCOUNT_ROWS)[2:4] == [(3, "River USD", "USD", "exchange", 1, 0),
                                        (4, "River BTC", "BTC", "exchange", 1, 0)]


def test_the_seed_puts_back_exchange_1(tmp_path):
    db = tmp_path / "btctx.db"
    init_db(engine_for(db))
    con = sqlite3.connect(str(db))
    con.executescript("DELETE FROM exchanges;")
    con.close()
    init_db(engine_for(db))
    assert q(db, "SELECT id, name, sends_1099da FROM exchanges") == [(1, "Exchange", 1)]


# ---------------------------------------------------------------------------
# The pre-2.0 copy (2.0 spec 5.3, Q21): a 1.x database's copy before 2.0's
# upgrade is a kind of its own, never pruned
# ---------------------------------------------------------------------------
ONE_X = sorted(r.revision for r in migrate._script().walk_revisions() if r.revision not in migrate.revisions_of_2_0())


@pytest.mark.parametrize("revision", ONE_X)
def test_a_1x_database_gets_a_pre_2_0_copy_named_after_its_revision(tmp_path, revision):
    db = tmp_path / "btctx.db"
    _move_to(db, revision)
    result = upgrade_database(engine_for(db))
    assert result.backup.name.startswith(f"btctx-pre-2.0-from-{revision}-")
    assert migrate.backup_copies(db, "pre-2.0") == [result.backup]
    assert migrate.backup_copies(db, "before") == []
    assert q(result.backup, "SELECT version_num FROM alembic_version") == [(revision,)]


def test_an_unversioned_databases_copy_says_so(v070):
    result = init_db(engine_for(v070))
    assert result.backup.name.startswith("btctx-pre-2.0-from-unversioned-")


def test_a_2_0_databases_upgrade_copy_is_an_ordinary_one():
    assert migrate.copy_for("0012") == ("pre-2.0", "from-0012", None)
    assert migrate.copy_for(None) == ("pre-2.0", "from-unversioned", None)
    assert migrate.copy_for("0100") == ("before", f"schema-{head_revision()}", migrate.BACKUPS_KEPT)


def test_pre_2_0_copies_are_kept_through_going_back_and_later_copies(tmp_path):
    """Seven upgrades from 1.x (six trips back and up again) keep seven
    copies, more than any other kind keeps; six more copies of the ordinary
    kind (later upgrades, restores) push none out."""
    db = tmp_path / "btctx.db"
    _move_to(db, "0012")
    for _ in range(6):
        upgrade_database(engine_for(db))
        _move_to(db, "0012", how=command.downgrade)
    upgrade_database(engine_for(db))
    kept = migrate.backup_copies(db, "pre-2.0")
    assert len(kept) == 7 > migrate.BACKUPS_KEPT
    for n in range(6):
        migrate.backup_sqlite(db, f"schema-{n}")
    assert migrate.backup_copies(db, "pre-2.0") == kept
    assert len(migrate.backup_copies(db, "before")) == migrate.BACKUPS_KEPT
    assert migrate.prune_backups(db, None, "pre-2.0") == []
    assert migrate.backup_copies(db, "pre-2.0") == kept
