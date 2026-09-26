# backend/services/backup.py

import hashlib
import hmac
import logging
import os
import sqlite3
import struct
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
_HEADER_LENGTH = len(MAGIC) + 1 + 4


# === Utils ===
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
        salt = blob[_HEADER_LENGTH:_HEADER_LENGTH + SALT_LENGTH]
        iv = blob[_HEADER_LENGTH + SALT_LENGTH:_HEADER_LENGTH + SALT_LENGTH + IV_LENGTH]
        body, tag = blob[:-MAC_LENGTH], blob[-MAC_LENGTH:]
        keys = _derive_key(password, salt, iterations, 2 * KEY_LENGTH)
        enc_key, mac_key = keys[:KEY_LENGTH], keys[KEY_LENGTH:]
        if not hmac.compare_digest(_mac(mac_key, body), tag):
            raise ValueError("❌ Failed to decrypt backup. Wrong password?")
        return _decrypt_data(body[_HEADER_LENGTH + SALT_LENGTH + IV_LENGTH:], enc_key, iv)

    # v1: no header, fixed iterations, no MAC
    salt = blob[:SALT_LENGTH]
    iv = blob[SALT_LENGTH:SALT_LENGTH + IV_LENGTH]
    key = _derive_key(password, salt, LEGACY_ITERATIONS)
    try:
        return _decrypt_data(blob[SALT_LENGTH + IV_LENGTH:], key, iv)
    except Exception as e:
        raise ValueError("❌ Failed to decrypt backup. Wrong password?") from e

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

    # Owner-only, like the database itself.
    fd = os.open(output_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(fd, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(encrypt_backup(db_data, password))

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

    decrypted = decrypt_backup(encrypted_file.read_bytes(), password)
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
