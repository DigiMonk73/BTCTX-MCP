#!/usr/bin/env bash
# Daily SQLite backup of a BitcoinTX database (e.g. from cron), keeping
# 60 days of dated copies. sqlite3 .backup copies safely while the app runs,
# WAL included; a plain cp could catch a half-written page.
#
# Usage: scripts/backup-db.sh [path/to/btctx.db]
# The database is the argument, else $DATABASE_FILE. Copies go to
# $BACKUP_DIR, else daily-backups/ beside the database: not its backups/,
# where the app keeps only its last few pre-upgrade copies.

set -euo pipefail

DB_PATH="${1:-${DATABASE_FILE:-}}"
if [ -z "$DB_PATH" ]; then
    echo "usage: $0 path/to/btctx.db (or set DATABASE_FILE)" >&2
    exit 2
fi
BACKUP_DIR="${BACKUP_DIR:-$(dirname "$DB_PATH")/daily-backups}"
KEEP_DAYS=60

# sqlite3's .backup takes the file name in single quotes
case "$BACKUP_DIR" in
    *"'"*) echo "$0: the backup folder's path can't contain a ' ($BACKUP_DIR)" >&2; exit 2 ;;
esac

DATE=$(date +%Y-%m-%d)
BACKUP_FILE="$BACKUP_DIR/btctx_${DATE}.db"

if [ ! -f "$DB_PATH" ]; then
    echo "$(date -Iseconds) ERROR: Database not found at $DB_PATH" >&2
    exit 1
fi

mkdir -p "$BACKUP_DIR"
sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

echo "$(date -Iseconds) Backed up to $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

find "$BACKUP_DIR" -name "btctx_*.db" -mtime +$KEEP_DAYS -delete -print | while read -r f; do
    echo "$(date -Iseconds) Pruned old backup: $f"
done
