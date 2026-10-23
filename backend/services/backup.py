"""
The encrypted backup: a consistent snapshot of the SQLite database, sealed
with a key derived from the owner's password, and its restore.
"""

import hashlib
import hmac
import logging
import os
import re
import sqlite3
import struct
import tempfile
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

from pydantic import ValidationError
from sqlalchemy import Date, DateTime, Numeric, create_engine, text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.backends import default_backend
import secrets

logger = logging.getLogger(__name__)

# The database DATABASE_FILE names, as database.py resolves it (/data/btctx.db
# in Docker and StartOS).
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
_PROJECT_ROOT = os.path.dirname(_BASE_DIR)
_DATABASE_FILE_ENV = os.getenv("DATABASE_FILE", "backend/bitcoin_tracker.db")
_DATABASE_FILE = (
    _DATABASE_FILE_ENV if os.path.isabs(_DATABASE_FILE_ENV)
    else os.path.join(_PROJECT_ROOT, _DATABASE_FILE_ENV)
)
DB_PATH = Path(_DATABASE_FILE)
KEY_LENGTH = 32  # AES-256
SALT_LENGTH = 16
IV_LENGTH = 16
MAC_LENGTH = 32  # HMAC-SHA256

# Backup file format.
#   v2 (0.9.2+): MAGIC | version (1 byte) | PBKDF2 iterations (4 bytes, big
#       endian) | salt | iv | AES-256-CBC ciphertext | HMAC-SHA256 tag.
#       One PBKDF2-SHA256 derivation gives the encryption key and the MAC
#       key; the tag covers everything before it (encrypt-then-MAC), so a
#       wrong password or a damaged file is caught before decrypting.
#       600,000 iterations (OWASP's recommendation for PBKDF2-SHA256); the
#       count is in the file, so it can rise later without breaking restores.
#   v1 (up to 0.9.1): salt | iv | ciphertext, 100,000 iterations, no MAC.
#       Still restored.
MAGIC = b"BTCTX-BACKUP"
FORMAT_VERSION = 2
PBKDF2_ITERATIONS = 600_000
LEGACY_ITERATIONS = 100_000
# The count a v2 file may ask for. It comes from the file, so without a limit
# a crafted file could ask for billions of rounds and tie up the server.
MIN_ITERATIONS = 100_000
MAX_ITERATIONS = 5_000_000
_HEADER_LENGTH = len(MAGIC) + 1 + 4
SQLITE_HEADER = b"SQLite format 3\x00"
# Why a restore was refused: plain words, never SQL
NOT_OURS = "This backup can't be restored: it holds database objects BitcoinTX doesn't make."
DAMAGED = "This file isn't a BitcoinTX backup, or it's damaged."
NOT_UPGRADED = "This backup can't be restored: its database couldn't be brought up to this version of BitcoinTX."
DOESNT_FIT = "This backup can't be restored: its {table} rows don't fit BitcoinTX's database."
ONE_LOGIN = "This backup can't be restored: it holds more than one login, and BitcoinTX has one."
ACCOUNTS_DONT_FIT = "This backup can't be restored: its accounts don't fit."
NEWER = ("This backup can't be restored: it was made by a newer version of BitcoinTX. Update BitcoinTX, "
         "or restore a backup made with this version.")
BUSY = "Another restore is running: wait for it to finish, then try again."
SAVING = ("BitcoinTX was busy saving something else, so the restore stopped. Your database is unchanged: "
          "try again in a moment.")
OLD_JOURNAL = ("BitcoinTX's database is still set up the way an older version's restore left it, and something "
               "else has it open, so the restore stopped. Your database is unchanged: restart BitcoinTX, then "
               "restore again.")
NOT_WRITTEN = ("This backup couldn't be restored: BitcoinTX couldn't write to its data folder. "
               "Your database is unchanged.")
# One restore at a time (one process serves the app): two at once would share
# the temporary files below
_restoring = threading.Lock()


def _derive_key(password: str, salt: bytes, iterations: int = LEGACY_ITERATIONS, length: int = KEY_LENGTH) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        iterations=iterations,
        backend=default_backend(),
    )
    return kdf.derive(password.encode())


def _mac(key: bytes, data: bytes) -> bytes:
    return hmac.new(key, data, hashlib.sha256).digest()


def encrypt_backup(db_data: bytes, password: str, iterations: int = PBKDF2_ITERATIONS) -> bytes:
    """A v2 backup file's bytes."""
    salt = secrets.token_bytes(SALT_LENGTH)
    iv = secrets.token_bytes(IV_LENGTH)
    keys = _derive_key(password, salt, iterations, 2 * KEY_LENGTH)
    enc_key, mac_key = keys[:KEY_LENGTH], keys[KEY_LENGTH:]
    body = MAGIC + bytes([FORMAT_VERSION]) + struct.pack(">I", iterations) + salt + iv
    body += _encrypt_data(db_data, enc_key, iv)
    return body + _mac(mac_key, body)


def decrypt_backup(blob: bytes, password: str) -> bytes:
    """The database inside a v2 or v1 backup; ValueError for a wrong password."""
    if blob.startswith(MAGIC):
        if len(blob) < _HEADER_LENGTH + SALT_LENGTH + IV_LENGTH + MAC_LENGTH:
            raise ValueError("This backup file is damaged (too short).")
        version = blob[len(MAGIC)]
        if version != FORMAT_VERSION:
            raise ValueError(f"This backup was made by a newer BitcoinTX (format {version}).")
        iterations = struct.unpack(">I", blob[len(MAGIC) + 1:_HEADER_LENGTH])[0]
        if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
            raise ValueError(
                f"This backup file is damaged or wasn't made by BitcoinTX "
                f"(key strength {iterations:,}, expected {MIN_ITERATIONS:,} to {MAX_ITERATIONS:,})."
            )
        salt =blob[_HEADER_LENGTH:_HEADER_LENGTH + SALT_LENGTH]
        iv = blob[_HEADER_LENGTH + SALT_LENGTH:_HEADER_LENGTH + SALT_LENGTH + IV_LENGTH]
        body, tag = blob[:-MAC_LENGTH], blob[-MAC_LENGTH:]
        keys = _derive_key(password, salt, iterations, 2 * KEY_LENGTH)
        enc_key, mac_key = keys[:KEY_LENGTH], keys[KEY_LENGTH:]
        if not hmac.compare_digest(_mac(mac_key, body), tag):
            raise ValueError("❌ Failed to decrypt backup. Wrong password?")
        try:
            return _decrypt_data(body[_HEADER_LENGTH + SALT_LENGTH + IV_LENGTH:], enc_key, iv)
        except ValueError as e:  # the library's own words (padding) aren't the owner's (#422)
            raise ValueError(DAMAGED) from e

    # v1: no header, fixed iterations, no MAC. A wrong key still unpads about
    # 1 time in 256, so the database header inside is the password check.
    salt = blob[:SALT_LENGTH]
    iv = blob[SALT_LENGTH:SALT_LENGTH + IV_LENGTH]
    key = _derive_key(password, salt, LEGACY_ITERATIONS)
    try:
        data = _decrypt_data(blob[SALT_LENGTH + IV_LENGTH:], key, iv)
    except Exception as e:
        raise ValueError("❌ Failed to decrypt backup. Wrong password?") from e
    if not data.startswith(SQLITE_HEADER):
        raise ValueError("❌ Failed to decrypt backup. Wrong password?")
    return data


def _encrypt_data(data: bytes, key: bytes, iv: bytes) -> bytes:
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(data) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    return encryptor.update(padded_data) + encryptor.finalize()


def _decrypt_data(encrypted_data: bytes, key: bytes, iv: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    padded_data = decryptor.update(encrypted_data) + decryptor.finalize()

    unpadder = padding.PKCS7(128).unpadder()
    return unpadder.update(padded_data) + unpadder.finalize()


def make_backup(password: str, output_file: Path, db_path: Path | None = None) -> None:
    db_path = Path(db_path or DB_PATH)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    # sqlite3's backup API gives a consistent snapshot even while the app
    # is writing (a plain file read could catch a half-written page). The
    # plain snapshot stays in memory, or (Python 3.10, no serialize) in a
    # private folder next to the database, never in the system's temp folder.
    src = sqlite3.connect(str(db_path))
    try:
        if hasattr(sqlite3.Connection, "serialize"):
            dst = sqlite3.connect(":memory:")
            try:
                src.backup(dst)
                db_data = dst.serialize()
            finally:
                dst.close()
        else:
            with tempfile.TemporaryDirectory(dir=db_path.parent, prefix=".backup-") as tmp:
                snapshot = Path(tmp) / "snapshot.db"
                dst = sqlite3.connect(str(snapshot))
                try:
                    src.backup(dst)
                finally:
                    dst.close()
                db_data = snapshot.read_bytes()
    finally:
        src.close()

    # Owner-only, like the database itself.
    fd = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(encrypt_backup(db_data, password))

    logger.info(f"Backup created at: {output_file}")


def restore_backup(
    password: str,
    encrypted_file: Path,
    db_path: Path | None = None,
    engine=None,
    carry_over: Callable[[Session | None, Session], None] | None = None,
):
    """
    Replace the database with a backup's. The live database stays as it was
    until the very end: the backup has decrypted, holds only BitcoinTX's kind
    of database objects, and has been upgraded to the current schema; then a
    new database is made by BitcoinTX's own migrations and only its own
    tables' and columns' rows are copied into it (_rebuild). Only then, under
    the live database's write lock (_swap), `carry_over`, given a session on
    the live database (None when there's none) and one on the new database,
    writes what this install keeps, and the live database is copied to
    <db dir>/backups/ and replaced.
    Any error deletes the temporary files and leaves the live database as it
    was. Returns the backup's MigrationResult.
    """
    from backend.migrate import backup_sqlite

    if engine is None:
        from backend.database import engine
    db_path = Path(db_path or DB_PATH)
    if not encrypted_file.exists():
        raise FileNotFoundError(f"Backup file not found: {encrypted_file}")

    decrypted = decrypt_backup(encrypted_file.read_bytes(), password)
    if not decrypted.startswith(SQLITE_HEADER):
        raise ValueError("This file isn't a BitcoinTX backup (no database inside).")
    if not _restoring.acquire(blocking=False):
        raise ValueError(BUSY)

    try:
        result = _restore_into(db_path, decrypted, carry_over, engine, backup_sqlite)
        engine.dispose()
    finally:
        _restoring.release()

    logger.info(f"Database restored from: {encrypted_file} (schema {result.from_revision or 'unversioned'} -> {result.to_revision})")
    return result


def _restore_into(db_path: Path, decrypted: bytes, carry_over, engine, backup_sqlite):
    """
    The backup's database beside the live one, the new one built from it,
    then the swap; the temporary files are deleted whatever happens. A file
    error (a folder that can't be written, a full disk) answers in plain
    words, never the server's paths.
    """
    staging = db_path.with_name(db_path.name + ".restoring")  # the backup's database
    rebuilt = db_path.with_name(db_path.name + ".rebuilding")  # the one that goes live
    try:
        try:
            # A restore cut short (the app quit) may have left a write-ahead
            # log here, which SQLite would apply to the next file of the same name
            _remove_database(staging)
            _remove_database(rebuilt)
            _write_owner_only(staging, decrypted)
            _write_owner_only(rebuilt, b"")
            result = _rebuild(staging, rebuilt)
            _swap(rebuilt, db_path, engine, backup_sqlite, carry_over)
        finally:
            _remove_database(staging)
            _remove_database(rebuilt)
    except OSError as e:
        logger.warning("Restore stopped: couldn't write the database files (%s)", e.strerror or type(e).__name__)
        raise ValueError(NOT_WRITTEN) from e
    return result


def _swap(rebuilt: Path, db_path: Path, engine, backup_sqlite, carry_over) -> None:
    """
    Under the live database's write lock, from reading what this install
    keeps to the new database taking the live one's place: `carry_over`
    reads it from the live database and writes it into the new one, a copy
    of the live database goes to backups/, then the swap. So a change saved
    before is kept, and one saved meanwhile waits for the lock, then is
    refused: in the rollback-journal mode BitcoinTX keeps its database in
    (database.init_db, and _write_locked), SQLite won't write a file that
    has been replaced. Another save holding the lock past 5 s stops the
    restore.
    """
    with _write_locked(db_path, engine) as live:
        if carry_over is not None:
            _write_what_is_kept(carry_over, live, rebuilt)
        if live is not None:
            kept = backup_sqlite(db_path, "restore")
            logger.info(f"Database being replaced was saved to: {kept}")
        engine.dispose()
        # What SQLite keeps beside the live database (in its rollback-journal
        # mode, nothing while this lock is held): left next to the new one, a
        # write-ahead log or journal would be applied to it.
        _remove_side_files(db_path)
        os.replace(rebuilt, db_path)


@contextmanager
def _write_locked(db_path: Path, engine) -> Iterator[Session | None]:
    """
    A session on the live database holding its write lock until the block
    ends (None when there's no live database yet), in SQLite's rollback
    journal. A live database still in write-ahead-log mode (an older
    version's restore left it so, and something had it open at the start)
    is switched first, as init_db does; while something else keeps it so,
    the restore stops: there a save that waited for the lock would go into
    the replaced file's log, answered as saved. ValueError for that, or when
    another save held the lock longer than 5 s: nothing was changed.
    """
    from backend.database import take_write_lock, use_rollback_journal

    if not db_path.exists():
        yield None
        return
    use_rollback_journal(engine)
    live = create_engine(f"sqlite:///{db_path}", poolclass=NullPool)
    try:
        with Session(live) as session:
            if not take_write_lock(session):
                logger.warning("Restore stopped: another save held the database's lock")
                raise ValueError(SAVING)
            try:
                if session.execute(text("PRAGMA journal_mode")).scalar() == "wal":
                    logger.warning("Restore stopped: the database is still in write-ahead-log mode")
                    raise ValueError(OLD_JOURNAL)
                yield session
            finally:
                session.rollback()
    finally:
        live.dispose()


def _write_what_is_kept(carry_over: Callable[[Session | None, Session], None], live: Session | None,
                        rebuilt: Path) -> None:
    new = create_engine(f"sqlite:///{rebuilt}", poolclass=NullPool)
    try:
        with Session(new) as restored:
            carry_over(live, restored)
    finally:
        new.dispose()


def _write_owner_only(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)  # owner-only from the start, also over a leftover file
    with os.fdopen(fd, "wb") as f:
        f.write(data)


def _rebuild(staging: Path, rebuilt: Path):
    """
    Check and upgrade the backup's database, make the new one with the
    migrations (as a fresh install does), copy the backup's own data into
    it, seed the fixed accounts and require one login and whole exchanges.
    Database errors come back in plain words, never SQL.
    """
    from backend.database import seed_defaults
    from backend.migrate import MigrationError, upgrade_database

    try:
        result = _check_and_upgrade(staging)
        new = create_engine(f"sqlite:///{rebuilt}", poolclass=NullPool)
        try:
            upgrade_database(new, backup=False)
            _copy_own_data(new, staging)
            seed_defaults(new)
            _require_one_login(new)
            _require_whole_exchanges(new)
            _read_as_the_app_does(new)
        finally:
            new.dispose()
        return result
    except MigrationError as e:
        message = _not_upgraded(e)
        logger.warning("Restore refused: the backup's database couldn't be upgraded (%s)",
                       _reason(e.__cause__) if e.__cause__ else message)
        raise ValueError(message) from e
    except SQLAlchemyError as e:
        logger.warning("Restore refused: the backup's database couldn't be read (%s)", _reason(e))
        raise ValueError(DAMAGED) from e
    except OSError as e:
        logger.warning("Restore stopped: couldn't write the database files (%s)", e.strerror or type(e).__name__)
        raise ValueError(NOT_WRITTEN) from e
    except ValueError:
        raise
    except Exception as e:  # e.g. alembic's own words on a stamp it can't read
        logger.warning("Restore refused: the backup's database couldn't be read (%s)", type(e).__name__)
        raise ValueError(DAMAGED) from e


def _check_and_upgrade(staging: Path):
    """The backup's database, checked before anything runs in it, then
    brought to the current schema so its rows fit the new database's."""
    from backend.migrate import upgrade_database

    staged = create_engine(f"sqlite:///{staging}", poolclass=NullPool)
    try:
        _refuse_objects_not_ours(staged)
        return upgrade_database(staged, backup=False)
    finally:
        staged.dispose()


def _refuse_objects_not_ours(staged) -> None:
    """
    Only BitcoinTX's kind of database is restored: ordinary tables and
    indexes, the only objects its migrations make, with its core tables. A
    trigger or a view runs SQL that isn't BitcoinTX's whenever the app reads
    or writes; a virtual table runs a module's code on the backup's data; a
    generated column, or an index on an expression or with a WHERE, works
    out values with the backup's own expression as its rows are read or
    written (BitcoinTX's migrations do both, upgrading the backup's copy),
    and a stored one keeps them. BitcoinTX's migrations make none of these.
    A table's CHECK rules stay allowed (no pragma lists them, and a
    backup's own table definitions never reach the live database): they
    run only in the backup's copy. Read from the schema alone (sqlite_master
    and the pragmas on it), so nothing in the backup runs first.
    """
    from backend.migrate import CORE_TABLES

    with staged.connect() as conn:
        rows = conn.exec_driver_sql("SELECT type, name, sql FROM sqlite_master").all()
        if any(kind not in ("table", "index") or _virtual(sql) for kind, _, sql in rows):
            raise ValueError(NOT_OURS)
        tables = [name for kind, name, _ in rows if kind == "table"]
        if any(_generated_columns(conn, table) or _indexes_with_expressions(conn, table) for table in tables):
            raise ValueError(NOT_OURS)
    if not CORE_TABLES <= {name.lower() for name in tables}:
        raise ValueError(DAMAGED)


def _generated_columns(conn, table: str) -> bool:
    """Whether a table has a generated column (table_xinfo's hidden is 2
    for a VIRTUAL one, 3 for a STORED one)."""
    return any(row[6] in (2, 3) for row in conn.exec_driver_sql(f"PRAGMA table_xinfo({_quoted(table)})"))


def _indexes_with_expressions(conn, table: str) -> bool:
    """Whether one of a table's indexes has a WHERE (index_list's partial
    is 1) or is on an expression (index_xinfo's cid is -2 for one)."""
    indexes = conn.exec_driver_sql(f"PRAGMA index_list({_quoted(table)})").all()
    return any(partial for _, _, _, _, partial in indexes) or any(
        row[1] == -2 for index in indexes for row in conn.exec_driver_sql(f"PRAGMA index_xinfo({_quoted(index[1])})"))


def _virtual(sql: str | None) -> bool:
    """Whether a schema statement is CREATE VIRTUAL TABLE (SQLite reads a
    comment as a space, and keywords in any case)."""
    words = re.sub(r"/\*.*?(?:\*/|$)|--[^\n]*", " ", sql or "", flags=re.S).split()
    return [word.upper() for word in words[:2]] == ["CREATE", "VIRTUAL"]


def _copy_own_data(new, staging: Path) -> None:
    """
    Copy the backup's rows of every table BitcoinTX's migrations made in the
    new database (but alembic_version, which they set), in that table's
    columns, ids kept. Nothing else in the backup comes along: other tables
    or columns, its table definitions, its indexes. A table or column
    BitcoinTX needs that the backup lacks, or rows the new tables refuse (a
    duplicate key, a missing value), stop the restore. The app doesn't turn
    on SQLite's foreign keys, so the copy's order doesn't matter.
    """
    with new.connect() as conn:
        conn.exec_driver_sql("ATTACH DATABASE ? AS staged", (str(staging),))
        tables = conn.exec_driver_sql("SELECT name FROM main.sqlite_master WHERE type = 'table'").scalars().all()
        for table in tables:
            if table != "alembic_version" and not table.startswith("sqlite_"):
                _copy_table(conn, table)
        conn.commit()


def _copy_table(conn, table: str) -> None:
    columns = [row[1] for row in conn.exec_driver_sql(f"PRAGMA main.table_info({_quoted(table)})")]
    present = {row[1].lower() for row in conn.exec_driver_sql(f"PRAGMA staged.table_info({_quoted(table)})")}
    missing = [column for column in columns if column.lower() not in present]
    if missing:
        what = f"the table {table}" if not present else f"{table}.{missing[0]}"
        raise ValueError(f"This backup can't be restored: its database lacks {what}, which BitcoinTX needs.")
    names = ", ".join(_quoted(column) for column in columns)
    if _rows_without_a_key(conn, table):
        raise ValueError(DOESNT_FIT.format(table=table))
    try:
        conn.exec_driver_sql(
            f"INSERT INTO main.{_quoted(table)} ({names}) SELECT {names} FROM staged.{_quoted(table)}")
    except IntegrityError as e:
        logger.warning("Restore refused: the backup's %s rows don't fit (%s)", table, _reason(e))
        raise ValueError(DOESNT_FIT.format(table=table)) from e
    if _text_in_a_number_column(conn, table):
        raise ValueError(DOESNT_FIT.format(table=table))


# Declared types whose values the app reads as numbers (SQLAlchemy's Integer,
# Numeric, Boolean): a text there (copied as it is) fails every later read
NUMBER_TYPES = ("INTEGER", "NUMERIC", "BOOLEAN", "DECIMAL", "REAL", "FLOAT")


def _rows_without_a_key(conn, table: str) -> bool:
    """Whether a row has no primary key (SQLite would quietly give it one)."""
    keys = [row[1] for row in conn.exec_driver_sql(f"PRAGMA main.table_info({_quoted(table)})") if row[5]]
    where = " OR ".join(f"{_quoted(key)} IS NULL" for key in keys)
    return bool(keys) and conn.exec_driver_sql(
        f"SELECT EXISTS (SELECT 1 FROM staged.{_quoted(table)} WHERE {where})").scalar()


def _text_in_a_number_column(conn, table: str) -> bool:
    """Whether a copied number column holds something that isn't a number."""
    numbers = [row[1] for row in conn.exec_driver_sql(f"PRAGMA main.table_info({_quoted(table)})")
               if row[2].upper().startswith(NUMBER_TYPES)]
    where = " OR ".join(f"typeof({_quoted(column)}) NOT IN ('integer', 'real', 'null')" for column in numbers)
    return bool(numbers) and conn.exec_driver_sql(
        f"SELECT EXISTS (SELECT 1 FROM main.{_quoted(table)} WHERE {where})").scalar()


def _quoted(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _read_as_the_app_does(new) -> None:
    """
    Every copied row read through BitcoinTX's models, as the app will read
    it (its types turn stored text into dates and numbers), and as the
    screens and reports go on to use it (_require_usable): a value it can't
    read would fail every later read of that table, so it refuses the
    restore now.
    """
    from backend.models import Base

    with Session(new) as session:
        for mapper in Base.registry.mappers:
            checks = _checks(mapper)
            try:
                for row in session.query(mapper.class_).yield_per(1000):
                    _require_usable(row, checks)
            except (ValueError, TypeError, ArithmeticError, SQLAlchemyError) as e:
                logger.warning("Restore refused: a %s row can't be read (%s)", mapper.local_table.name, _reason(e))
                raise ValueError(DOESNT_FIT.format(table=mapper.local_table.name)) from e
            session.expunge_all()


# How big a restored number may be, by what it holds (#460): no ledger with
# real figures comes near these, and past them a page can fail.
# - A transaction's amount and fee (whatever their account), and a lot's or
#   a disposal's bitcoin, a part of one: below 10^10, the rule every save
#   has checked since 0.9.2 (schemas.transaction.BTC_DIGITS).
# - A stored price: below $10^15 a bitcoin, far above any a source has
#   given, so a lot's bitcoin times its price stays below 10^25, which the
#   reports round to cents within Decimal's 28 digits.
# - Any other figure (a dollar value, a lot's cost, a ledger line): below
#   10^17. A save takes 16 digits at most (a lot's cost adds its fee), and
#   the dashboard's average cost divides a lot's cost by as little as a
#   satoshi (10^-8), then rounds it to cents within those 28 digits.
# - But a Sell's or Withdrawal's basis and gain, which add up its lots'
#   (compute_sell_summary_from_disposals): below 10^22 (a sale of a
#   million lots, each at a save's limit, would pass it).
NUMBER_LIMITS = {
    **dict.fromkeys([("transactions", "amount"), ("transactions", "fee_amount"), ("bitcoin_lots", "total_btc"),
                     ("bitcoin_lots", "remaining_btc"), ("lot_disposals", "disposed_btc")], Decimal(10) ** 10),
    **dict.fromkeys([("btc_price_daily", "usd"), ("btc_price_hourly", "usd")], Decimal(10) ** 15),
}
FIGURES_BELOW = Decimal(10) ** 17
SALES, SALE_TOTALS = ("Sell", "Withdrawal"), ("cost_basis_usd", "realized_gain_usd")
SALE_TOTALS_BELOW = Decimal(10) ** 22
# The years a restored date or moment may fall in (#460): a timezone moves
# a moment by less than a day, so its local date stays within Python's
# years (1 to 9999), where the reports work. Every save since 0.9.2 keeps
# dates from Bitcoin's first block (2009-01-03) to the present.
USABLE_YEARS = range(2, 9999)


class _Checks(NamedTuple):
    """What _require_usable checks in one table's rows."""
    table: str
    numbers: dict[str, Decimal]  # column -> the limit its values stay below
    sale_numbers: dict[str, Decimal] | None  # a sale's (transactions only): its totals' limit raised
    dates: list[str]  # columns holding a date or a moment
    schema: type | None  # what the screens read its rows through (TransactionRead), if anything


def _checks(mapper) -> _Checks:
    """A table's checks, worked out once from its model's columns."""
    from backend.database import PlainDate, UTCDateTime
    from backend.models import Transaction
    from backend.schemas.transaction import TransactionRead

    table = mapper.local_table.name
    numbers, dates = {}, []
    for attr in mapper.column_attrs:
        kind = attr.columns[0].type
        if isinstance(kind, Numeric):
            numbers[attr.key] = NUMBER_LIMITS.get((table, attr.key), FIGURES_BELOW)
        elif isinstance(kind, (Date, DateTime, PlainDate, UTCDateTime)):
            dates.append(attr.key)
    if mapper.class_ is not Transaction:
        return _Checks(table, numbers, None, dates, None)
    return _Checks(table, numbers, {**numbers, **dict.fromkeys(SALE_TOTALS, SALE_TOTALS_BELOW)}, dates,
                   TransactionRead)


class _Unusable(ValueError):
    """A value the screens or reports can't use. Its text names the column,
    never the value, so the log may say it."""


def _require_usable(row, checks: _Checks) -> None:
    """
    A row as the screens and reports use it, stricter than the models
    (#460): its numbers finite and within their limits, its dates within
    USABLE_YEARS, and a transaction read through the API's TransactionRead
    as the list reads it (its type and broker reporting one of BitcoinTX's).
    Sources and purposes aren't checked: the app reads any (one saved as
    " gift ", #342; a withdrawal's of its own counts as Spent, #61).
    """
    numbers = checks.sale_numbers if checks.sale_numbers and row.type in SALES else checks.numbers
    for name, below in numbers.items():
        value = getattr(row, name)
        if value is not None and not abs(value) < below:  # an infinity fails it too
            raise _Unusable(f"{checks.table}.{name} is bigger than BitcoinTX's figures")
    for name in checks.dates:
        value = getattr(row, name)
        if value is not None and value.year not in USABLE_YEARS:
            raise _Unusable(f"{checks.table}.{name} is outside the years the reports use")
    if checks.schema is not None:
        try:
            checks.schema.model_validate(row)
        except ValidationError as e:
            fields = ", ".join(".".join(map(str, error["loc"])) for error in e.errors(include_input=False))
            raise _Unusable(f"{checks.table} can't be shown: {fields}") from e


def _require_one_login(new) -> None:
    """BitcoinTX has one login: a backup with more is refused (the restore
    keeps only this install's, on the first)."""
    with new.connect() as conn:
        if conn.exec_driver_sql("SELECT count(*) FROM users").scalar() != 1:
            raise ValueError(ONE_LOGIN)


def _require_whole_exchanges(new) -> None:
    """Each exchange has its two accounts, one in dollars and one in bitcoin,
    and an exchange's account names an exchange there is, which no other
    account does (2.0 spec 5.1, 5.11)."""
    with new.connect() as conn:
        broken = conn.exec_driver_sql("""
            SELECT 1 FROM exchanges e
             WHERE (SELECT count(*) FROM accounts a WHERE a.exchange_id = e.id) != 2
                OR NOT EXISTS (SELECT 1 FROM accounts a WHERE a.exchange_id = e.id AND a.currency = 'USD')
                OR NOT EXISTS (SELECT 1 FROM accounts a WHERE a.exchange_id = e.id AND a.currency = 'BTC')
            UNION ALL
            SELECT 1 FROM accounts a
             WHERE (a.kind = 'exchange') != (a.exchange_id IS NOT NULL)
                OR (a.exchange_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM exchanges e WHERE e.id = a.exchange_id))
            LIMIT 1""").first()
    if broken:
        raise ValueError(ACCOUNTS_DONT_FIT)


def _reason(error: BaseException) -> str:
    """SQLite's own words for an error, for the log: never the statement or
    its values, and on one line (they may hold the backup's names). A value
    the restore found unusable: which column it is in."""
    if isinstance(error, _Unusable):
        return str(error)
    words = str(error.orig) if isinstance(error, DBAPIError) else type(error).__name__
    return " ".join(words.split())[:200]


def _not_upgraded(e) -> str:
    """Why the backup's database couldn't be upgraded. A MigrationError that
    wraps another error carries that error's text, SQL included: plain words
    instead."""
    if e.__cause__ is not None:
        return NOT_UPGRADED
    if "written by a newer version" in str(e):  # its text names the backup's revision
        return NEWER
    return f"This backup can't be restored: {e}"


def _remove_database(path: Path) -> None:
    path.unlink(missing_ok=True)
    _remove_side_files(path)


def _remove_side_files(path: Path) -> None:
    """The files SQLite keeps beside a database: its write-ahead log and
    shared memory, or its rollback journal."""
    for suffix in ("-wal", "-shm", "-journal"):
        path.with_name(path.name + suffix).unlink(missing_ok=True)
