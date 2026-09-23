# backend/services/backup.py

import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes, padding
from cryptography.hazmat.backends import default_backend
import secrets

logger = logging.getLogger(__name__)

# === Constants ===
# Use the same DATABASE_FILE env var as database.py for consistency
# This ensures backup/restore works correctly in Docker/StartOS where DB is at /data/btctx.db
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
PBKDF2_ITERATIONS = 100_000

# === Utils ===
def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
        backend=default_backend(),
    )
    return kdf.derive(password.encode())

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

# === Public API ===

SQLITE_HEADER = b"SQLite format 3\x00"


def make_backup(password: str, output_file: Path, db_path: Optional[Path] = None) -> None:
    db_path = Path(db_path or DB_PATH)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    # sqlite3's backup API gives a consistent snapshot even while the app
    # is writing (a plain file read could catch a half-written page).
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "snapshot.db"
        src, dst = sqlite3.connect(str(db_path)), sqlite3.connect(str(snapshot))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        db_data = snapshot.read_bytes()

    salt = secrets.token_bytes(SALT_LENGTH)
    iv = secrets.token_bytes(IV_LENGTH)
    key = _derive_key(password, salt)
    encrypted = _encrypt_data(db_data, key, iv)

    with open(output_file, "wb") as f:
        f.write(salt + iv + encrypted)

    logger.info(f"Backup created at: {output_file}")


def restore_backup(password: str, encrypted_file: Path, db_path: Optional[Path] = None, engine=None):
    """
    Replace the database with a decrypted backup, upgraded to the current
    schema. The live database is only touched once the backup has decrypted,
    is a SQLite file and has migrated successfully; the database it replaces
    is kept in <db dir>/backups/. Returns the MigrationResult of the backup.
    """
    from backend.migrate import MigrationError, backup_sqlite, upgrade_database
    from backend.database import seed_defaults

    if engine is None:
        from backend.database import engine
    db_path = Path(db_path or DB_PATH)
    if not encrypted_file.exists():
        raise FileNotFoundError(f"Backup file not found: {encrypted_file}")

    blob = encrypted_file.read_bytes()
    salt = blob[:SALT_LENGTH]
    iv = blob[SALT_LENGTH:SALT_LENGTH + IV_LENGTH]
    encrypted_data = blob[SALT_LENGTH + IV_LENGTH:]
    key = _derive_key(password, salt)

    try:
        decrypted = _decrypt_data(encrypted_data, key, iv)
    except Exception as e:
        raise ValueError("❌ Failed to decrypt backup. Wrong password?") from e
    if not decrypted.startswith(SQLITE_HEADER):
        raise ValueError("This file isn't a BitcoinTX backup (no database inside).")

    staging = db_path.with_name(db_path.name + ".restoring")
    staging.write_bytes(decrypted)
    os.chmod(staging, 0o600)
    staged = create_engine(f"sqlite:///{staging}", poolclass=NullPool)
    try:
        result = upgrade_database(staged, backup=False)
        seed_defaults(staged)
    except MigrationError as e:
        staging.unlink(missing_ok=True)
        raise ValueError(f"This backup can't be restored: {e}") from e
    except Exception:
        staging.unlink(missing_ok=True)
        raise
    finally:
        staged.dispose()

    if db_path.exists():
        kept = backup_sqlite(db_path, "restore")
        logger.info(f"Database being replaced was saved to: {kept}")
    engine.dispose()
    os.replace(staging, db_path)
    engine.dispose()

    logger.info(f"Database restored from: {encrypted_file} (schema {result.from_revision or 'unversioned'} -> {result.to_revision})")
    return result
