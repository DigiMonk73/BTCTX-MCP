"""
backend/migrate.py

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
BASELINE = "0001"
BACKUP_DIRNAME = "backups"
# Tables without which a database can't be a BitcoinTX ledger at all.
CORE_TABLES = {"users", "accounts", "transactions"}


class MigrationError(RuntimeError):
    """The database can't be brought to the current schema automatically."""


@dataclass
class MigrationResult:
    from_revision: Optional[str]
    to_revision: str
    adopted: bool = False
    repairs: List[str] = field(default_factory=list)
    backup: Optional[Path] = None

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


def current_revision(connection: Connection) -> Optional[str]:
    return MigrationContext.configure(connection).get_current_revision()


def _app_tables(connection: Connection) -> set:
    return {
        t for t in inspect(connection).get_table_names()
        if t != "alembic_version" and not t.startswith("sqlite_")
    }


def sqlite_file(engine: Engine) -> Optional[Path]:
    if engine.dialect.name != "sqlite":
        return None
    db = engine.url.database
    if not db or db == ":memory:" or db.startswith("file:"):
        return None
    return Path(db)


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------
def backup_sqlite(db_path: Path, label: str) -> Path:
    """Consistent copy of a live SQLite file into <dir>/backups/ (mode 600)."""
    dest_dir = db_path.parent / BACKUP_DIRNAME
    dest_dir.mkdir(mode=0o700, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = dest_dir / f"{db_path.stem}-before-{label}-{stamp}.db"
    n = 1
    while dest.exists():
        n += 1
        dest = dest_dir / f"{db_path.stem}-before-{label}-{stamp}-{n}.db"
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    os.chmod(dest, 0o600)
    return dest


# ---------------------------------------------------------------------------
# Adopting databases created before migrations existed
# ---------------------------------------------------------------------------
def _baseline_reference() -> Tuple[Dict[str, str], Dict[str, str], Dict[str, list]]:
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


def adopt_unversioned(conn: Connection) -> List[str]:
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
    repairs: List[str] = []

    for table, ddl in ref_tables.items():
        if table not in have:
            conn.exec_driver_sql(ddl)
            repairs.append(f"created table {table}")
            continue
        existing = {row[1] for row in conn.exec_driver_sql(f'PRAGMA table_info("{table}")')}
        for _cid, name, col_type, notnull, default, _pk in ref_columns[table]:
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
            repairs.append(f"added column {table}.{name}")

    existing_indexes = {
        row[0] for row in conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type = 'index'")
    }
    for name, ddl in ref_indexes.items():
        if name not in existing_indexes:
            conn.exec_driver_sql(ddl)
            repairs.append(f"created index {name}")

    cfg = alembic_config()
    cfg.attributes["connection"] = conn
    command.stamp(cfg, BASELINE)
    return repairs


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
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
