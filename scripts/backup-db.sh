#!/usr/bin/env bash
# Daily SQLite backup of a BitcoinTX database (e.g. from cron), keeping
# 60 days of dated copies. sqlite3 .backup copies safely while the app runs,
# WAL included; a plain cp could catch a half-written page.

set -euo pipefail

PROJECT_DIR="/home/ubuntu76/Projects/BTCTX-org"
DB_PATH="$PROJECT_DIR/backend/bitcoin_tracker.db"
BACKUP_DIR="$PROJECT_DIR/backups"
KEEP_DAYS=60

DATE=$(date +%Y-%m-%d)
BACKUP_FILE="$BACKUP_DIR/btctx_${DATE}.db"

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB_PATH" ]; then
    echo "$(date -Iseconds) ERROR: Database not found at $DB_PATH" >&2
    exit 1
fi

sqlite3 "$DB_PATH" ".backup '$BACKUP_FILE'"

echo "$(date -Iseconds) Backed up to $BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"

find "$BACKUP_DIR" -name "btctx_*.db" -mtime +$KEEP_DAYS -delete -print | while read f; do
    echo "$(date -Iseconds) Pruned old backup: $f"
done
