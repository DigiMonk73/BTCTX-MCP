"""
Brings a BitcoinTX SQLite database to the current schema (Alembic "head").
Runs at every startup (database.init_db) and on a restored backup.

    fresh database (no tables)      -> run every migration from 0001
    versioned, behind head          -> back up, upgrade
    versioned, at head              -> nothing
    versioned, unknown revision     -> refuse: written by a newer BitcoinTX
    unversioned, has tables         -> back up, repair to the 0001 baseline,
                                       stamp 0001, upgrade
      (every install from before migrations existed: v0.7.x and older were
      built by create_all(), which never adds columns or indexes to a table
      that already exists)

Migrations run on their own connection with real transactional DDL, so a
failed upgrade rolls back completely; the pre-upgrade copy in
<database dir>/backups/ is a second safety net.
"""

from __future__ import annotations

import datetime
import logging
import os
import sqlite3
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BASELINE = "0001"
BACKUP_DIRNAME = "backups"
# Pre-upgrade / pre-restore copies kept in <db dir>/backups/ (newest first).
BACKUPS_KEPT = 5
# Copies the AI key asked for (POST /api/backup/ai-copy), or made before its
# first change in an hour (PUT or DELETE /api/transactions/{id}, label
# AI_CHANGE_LABEL), kept apart: the newest 3, and for AI_DAYS_HELD days the
# oldest of them and the first made before a change each day
# (_ai_copies_held), so for a week they hold the ledger from before each
# day's changes, however many copies are made after them. At most 11.
AI_COPIES_KEPT = 3
AI_DAYS_HELD = 7  # UTC days: today and the 6 before it
AI_CHANGE_LABEL = "before-changing"
# Copies before Ledger Review's hourly check is applied (#144), kept apart:
# applying one item at a time must not push out the pre-upgrade copy.
REVIEW_COPIES_KEPT = 5
# A copy being written: a name no listing of copies matches.
PARTIAL = ".partial-"
# Tables without which a database can't be a BitcoinTX ledger at all.
CORE_TABLES = {"users", "accounts", "transactions"}


class MigrationError(RuntimeError):
    """The database can't be brought to the current schema automatically."""


@dataclass
class MigrationResult:
    from_revision: str | None
    to_revision: str
    adopted: bool = False
    repairs: list[str] = field(default_factory=list)
    backup: Path | None = None

    @property
    def changed(self) -> bool:
        return self.from_revision != self.to_revision


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    return cfg


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def head_revision() -> str:
    return _script().get_current_head()


def current_revision(connection: Connection) -> str | None:
    return MigrationContext.configure(connection).get_current_revision()


def stamped_revision(connection: Connection) -> str | None:
    """The revision in alembic_version, by plain SQL; None without the table.
    For the health check: MigrationContext logs two INFO lines per call, and
    StartOS asks every 30 seconds."""
    if "alembic_version" not in inspect(connection).get_table_names():
        return None
    return connection.execute(text("SELECT version_num FROM alembic_version")).scalar()


def _app_tables(connection: Connection) -> set:
    return {
        t for t in inspect(connection).get_table_names()
        if t != "alembic_version" and not t.startswith("sqlite_")
    }


def sqlite_file(engine: Engine) -> Path | None:
    if engine.dialect.name != "sqlite":
        return None
    db = engine.url.database
    if not db or db == ":memory:" or db.startswith("file:"):
        return None
    return Path(db)


# Backups
def backup_sqlite(db_path: Path, label: str, kind: str = "before", keep: int = BACKUPS_KEPT) -> Path:
    """
    Consistent copy of a live SQLite file into <dir>/backups/ (mode 600),
    named <stem>-<kind>-<label>-<time>.db. Each kind ("before": pre-upgrade
    and pre-restore; "ai": asked for with the AI key, or made before its
    changes; "review": before Ledger Review's hourly check is applied)
    keeps its own newest `keep` (and "ai" more: prune_backups), so one kind
    never pushes out the other.

    It is written under a name no listing matches and renamed once
    complete: a copy that fails (a full disk) leaves nothing that looks
    like a copy, which a check for a recent copy would take for one.
    """
    dest_dir = db_path.parent / BACKUP_DIRNAME
    dest_dir.mkdir(mode=0o700, exist_ok=True)
    _remove_unfinished(dest_dir)
    fd, name = tempfile.mkstemp(dir=dest_dir, prefix=PARTIAL, suffix=".db")  # mode 600
    os.close(fd)
    partial = Path(name)
    try:
        _copy_sqlite(db_path, partial)
        dest = _free_name(dest_dir, f"{db_path.stem}-{kind}-{label}")
        os.replace(partial, dest)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    prune_backups(db_path, keep, kind)
    return dest


def _remove_unfinished(dest_dir: Path) -> None:
    """Copies a stopped server left unfinished, with their journals (none is
    written for an hour)."""
    for partial in dest_dir.glob(f"{PARTIAL}*"):
        try:
            if time.time() - partial.stat().st_mtime > 3600:
                partial.unlink()
        except OSError as e:
            logger.warning("Couldn't remove an unfinished database copy %s: %s", partial, e)


def _copy_sqlite(db_path: Path, dest: Path) -> None:
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _free_name(dest_dir: Path, name: str) -> Path:
    """<name>-<time>.db in dest_dir, or with -2, -3... when that is taken."""
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"{name}-{stamp}.db"
    n = 1
    while dest.exists():
        n += 1
        dest = dest_dir / f"{name}-{stamp}-{n}.db"
    return dest


def backup_copies(db_path: Path, kind: str = "before", label: str | None = None) -> list[Path]:
    """This database's copies of one kind (and label, when given) in
    <dir>/backups/, newest first."""
    dest_dir = db_path.parent / BACKUP_DIRNAME
    pattern = f"{db_path.stem}-{kind}-{label}-*.db" if label else f"{db_path.stem}-{kind}-*.db"
    return sorted(
        dest_dir.glob(pattern),
        key=lambda p: (p.stat().st_mtime_ns, p.name),
        reverse=True,
    )


def prune_backups(db_path: Path, keep: int = BACKUPS_KEPT, kind: str = "before") -> list[Path]:
    """
    Keep the newest `keep` copies of one kind in <dir>/backups/ (the AI
    copies more: _ai_copies_held) and delete the others. Only files this
    module wrote (<stem>-<kind>-*.db) are touched. Returns the deleted paths.
    """
    dest_dir = db_path.parent / BACKUP_DIRNAME
    copies = backup_copies(db_path, kind)
    held = _ai_copies_held(db_path, copies) if kind == "ai" else set()
    removed = []
    for old in copies[keep:]:
        if old in held:
            continue
        try:
            old.unlink()
            removed.append(old)
        except OSError as e:
            logger.warning("Couldn't remove old database copy %s: %s", old, e)
    if removed:
        logger.info("Removed %d old database copies from %s", len(removed), dest_dir)
    return removed


def _ai_copies_held(db_path: Path, copies: list[Path]) -> set[Path]:
    """
    The AI copies (newest first) kept beyond the newest AI_COPIES_KEPT, from
    the last AI_DAYS_HELD UTC days: the oldest (the ledger from before those
    days' changes) and the first made before a change each day (the ledger
    from before that day's changes, with what the owner entered the days
    before).
    """
    today = datetime.datetime.now(datetime.timezone.utc).date()
    since = today - datetime.timedelta(days=AI_DAYS_HELD - 1)
    recent = [p for p in copies if _utc_day(p) >= since]
    first_each_day: dict[datetime.date, Path] = {}
    for p in reversed(recent):
        if p.name.startswith(f"{db_path.stem}-ai-{AI_CHANGE_LABEL}-"):
            first_each_day.setdefault(_utc_day(p), p)
    return set(recent[-1:]) | set(first_each_day.values())


def _utc_day(copy: Path) -> datetime.date:
    return datetime.datetime.fromtimestamp(copy.stat().st_mtime, datetime.timezone.utc).date()


# Adopting databases created before migrations existed
def _baseline_reference() -> tuple[dict[str, str], dict[str, str], dict[str, list]]:
    """(table DDL, index DDL, PRAGMA table_info per table) of revision 0001."""
    eng = create_engine("sqlite://")
    try:
        with eng.begin() as conn:
            cfg = alembic_config()
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, BASELINE)
            rows = conn.exec_driver_sql(
                "SELECT type, name, sql FROM sqlite_master "
                "WHERE sql IS NOT NULL AND tbl_name != 'alembic_version'"
            ).all()
            tables = {name: sql for kind, name, sql in rows if kind == "table"}
            indexes = {name: sql for kind, name, sql in rows if kind == "index"}
            columns = {t: conn.exec_driver_sql(f'PRAGMA table_info("{t}")').all() for t in tables}
    finally:
        eng.dispose()
    return tables, indexes, columns


def adopt_unversioned(conn: Connection) -> list[str]:
    """
    Repair a pre-migrations database to exactly what revision 0001 expects,
    then stamp it 0001. Only additive, data-preserving repairs are made:
    missing tables, missing indexes, and missing columns that are nullable or
    have a constant default. Anything else is a MigrationError. Extra tables
    or columns are left alone.
    """
    if conn.dialect.name != "sqlite":
        raise MigrationError("Adopting an unversioned database is only supported for SQLite.")

    have = _app_tables(conn)
    if not CORE_TABLES <= have:
        raise MigrationError(
            "This database has tables but isn't a BitcoinTX database "
            f"(missing {', '.join(sorted(CORE_TABLES - have))})."
        )

    ref_tables, ref_indexes, ref_columns = _baseline_reference()
    repairs: list[str] = []
    for table, ddl in ref_tables.items():
        if table not in have:
            conn.exec_driver_sql(ddl)
            repairs.append(f"created table {table}")
        else:
            repairs += _add_missing_columns(conn, table, ref_columns[table])
    repairs += _create_missing_indexes(conn, ref_indexes)

    cfg = alembic_config()
    cfg.attributes["connection"] = conn
    command.stamp(cfg, BASELINE)
    return repairs


def _add_missing_columns(conn: Connection, table: str, reference: list) -> list[str]:
    """The baseline's columns the table lacks, added when that keeps its rows."""
    existing = {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')}
    added = []
    for _cid, name, col_type, notnull, default, _pk in reference:
        if name in existing:
            continue
        if notnull and default is None:
            raise MigrationError(
                f"Column {table}.{name} is missing and required; this database "
                "can't be upgraded automatically."
            )
        ddl_col = f'ALTER TABLE "{table}" ADD COLUMN "{name}" {col_type}'
        if notnull:
            ddl_col += " NOT NULL"
        if default is not None:
            ddl_col += f" DEFAULT {default}"
        try:
            conn.exec_driver_sql(ddl_col)
        except Exception as e:  # e.g. SQLite refuses non-constant defaults
            raise MigrationError(f"Couldn't add missing column {table}.{name}: {e}") from e
        added.append(f"added column {table}.{name}")
    return added


def _create_missing_indexes(conn: Connection, reference: dict[str, str]) -> list[str]:
    existing = {
        row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    created = []
    for name, ddl in reference.items():
        if name not in existing:
            conn.exec_driver_sql(ddl)
            created.append(f"created index {name}")
    return created


# Entry point
def _transactional_engine(engine: Engine) -> Engine:
    """
    pysqlite doesn't wrap DDL in a transaction by default, so a migration that
    fails halfway would leave a half-changed schema. SQLAlchemy's documented
    recipe: let SQLAlchemy emit BEGIN itself.
    """
    if sqlite_file(engine) is None:
        return engine
    migrator = create_engine(engine.url, poolclass=NullPool)

    @event.listens_for(migrator, "connect")
    def _no_implicit_transactions(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(migrator, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    return migrator


def upgrade_database(engine: Engine, backup: bool = True) -> MigrationResult:
    """Bring the database behind `engine` to the latest schema."""
    script = _script()
    head = script.get_current_head()
    known = {rev.revision for rev in script.walk_revisions()}

    with engine.connect() as conn:
        rev = current_revision(conn)
        tables = _app_tables(conn)

    result = MigrationResult(from_revision=rev, to_revision=head)
    if rev == head:
        return result
    if rev is not None and rev not in known:
        raise MigrationError(
            f"This database is at schema revision {rev}, which this version of "
            "BitcoinTX doesn't know: it was written by a newer version. Update "
            "BitcoinTX, or restore a backup made with this version."
        )

    fresh = rev is None and not tables
    db_path = sqlite_file(engine)
    if backup and not fresh and db_path is not None and db_path.exists():
        result.backup = backup_sqlite(db_path, f"schema-{head}")
        logger.info("Backed up the database to %s before upgrading its schema", result.backup)

    migrator = _transactional_engine(engine)
    try:
        with migrator.begin() as conn:
            if rev is None and not fresh:
                result.repairs = adopt_unversioned(conn)
                result.adopted = True
            cfg = alembic_config()
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
    except MigrationError:
        raise
    except Exception as e:
        saved = f" Your data from before the upgrade is in {result.backup}." if result.backup else ""
        raise MigrationError(f"Upgrading the database schema to {head} failed: {e}.{saved}") from e
    finally:
        if migrator is not engine:
            migrator.dispose()
    # Connections pooled before the upgrade may hold stale schema info.
    engine.dispose()

    if result.adopted:
        logger.info(
            "Adopted an existing database into schema migrations%s",
            f" (repairs: {', '.join(result.repairs)})" if result.repairs else "",
        )
    logger.info("Database schema: %s -> %s", rev or ("new" if fresh else "unversioned"), head)
    return result
