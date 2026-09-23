# -----------------------------------------------------------------------------
# ✅ Testing & CI (start here)
# -----------------------------------------------------------------------------
# make hooks        → Install the pre-push hook (runs `make check-fast` before every push)
# make test         → Full hermetic Python suite (temp DB, no server, no internet)
# make test-fast    → Same minus the slow stress tests (~1 min)
# make smoke        → Start the real server on a temp DB and drive it end to end
# make lint         → Bug-level Python lint + frontend lint/type check
# make audit-deps   → Known-vulnerability scan of Python + npm dependencies
# make check        → Everything CI runs (except Docker/macOS builds)
# -----------------------------------------------------------------------------

PY ?= python3

.PHONY: hooks test test-fast smoke lint audit-deps check check-fast frontend-dist

hooks:
	git config core.hooksPath .githooks
	@echo "✓ pre-push hook installed (.githooks/pre-push)"

frontend-dist:
	@mkdir -p frontend/dist

test: frontend-dist
	$(PY) -m pytest -q

test-fast: frontend-dist
	$(PY) -m pytest -q -m "not slow"

smoke: frontend-dist
	$(PY) scripts/smoke_test.py

lint:
	$(PY) -m ruff check .
	cd frontend && npm run lint && npx tsc -b

audit-deps:
	$(PY) -m pip_audit -r backend/requirements.txt --ignore-vuln PYSEC-2026-1845
	cd frontend && npm audit --audit-level=high

check: lint test smoke audit-deps
	@echo "✓ all checks passed"

check-fast:
	.githooks/pre-push

# -----------------------------------------------------------------------------
# 💡 Legacy dev-database commands
# -----------------------------------------------------------------------------
# make audit         → Full audit loop: wipe DB, create default user + accounts, seed, run tests
# make reset-dev     → Fast rebuild: recreate DB → seed → test
# make reset-tx      → Re-run transactions + tests (no DB wipe or user reinit needed)
# make clean-db      → Delete SQLite database
# make create-db     → Run create_tables() (inserts default user + accounts)
# make seed-tx       → Load seed_transactions.json into DB
# make seed          → Shorthand for create-db → seed-tx
# make test-seed     → Run seed-data integrity tests against the dev DB
# make audit-fast    → Run tests but stop on first failure (quicker feedback)
# make debug         → Dump debug view: lots, balances, disposal mismatches
# make export        → Save audit output as JSON/CSV (if export script is enabled)
# make check-locks   → Print number of locked transactions in the database
# -----------------------------------------------------------------------------

.PHONY: audit clean-db seed test export debug create-db seed-tx reset-dev reset-tx audit-fast test-seed check-locks ensure-write

# ✅ Ensure DB is writable (if it exists)
ensure-write:
	@if [ -f backend/bitcoin_tracker.db ]; then chmod +w backend/bitcoin_tracker.db; fi

# 🧹 "Clean" target: Wipe DB then create fresh tables with default user + accounts only
clean: clean-db create-db
	@echo "🧹 Created a clean database with default user + accounts (no transactions)."


# 💥 Full audit pipeline
audit: clean-db seed test-seed

# 🧼 Delete the SQLite database
clean-db:
	rm -f backend/bitcoin_tracker.db

# 🧪 Recreate DB schema + default user + accounts, then seed TXs
seed: create-db seed-tx

# 🛠️ Run create_tables() (tables, admin user, accounts)
create-db: ensure-write
	python -c "from backend.database import create_tables; create_tables()"

# 📥 Load predefined test transactions
seed-tx: ensure-write
	python backend/tests/seed_transactions.py

# ✅ Run seed-data integrity tests
test-seed: ensure-write
	pytest backend/tests/test_seed_data_integrity.py

# 🔄 Rebuild DB, seed, test (fast dev reset)
reset-dev: clean-db seed test-seed

# 🔁 Only reseed + test (no DB wipe)
reset-tx: seed-tx test-seed

# ⚡ Run test suite but stop on first failure
audit-fast: ensure-write
	pytest backend/tests/test_seed_data_integrity.py --maxfail=1 -q

# 🪵 Dump balances, BTC lots, FIFO disposals
debug: ensure-write
	python backend/tests/dump_debug.py

# 📤 Export report files (CSV, JSON, etc.)
export: ensure-write
	python backend/tests/export_results.py

# 🔒 Count locked transactions
check-locks: ensure-write
	python -c "from backend.database import SessionLocal; from backend.models.transaction import Transaction; db = SessionLocal(); locked = db.query(Transaction).filter_by(is_locked=True).all(); print(f'{len(locked)} locked transaction(s)'); db.close()"

# 🔐 Create an encrypted backup file (AES-256)
backup:
	python -c "from backend.services.backup import make_backup; from pathlib import Path; make_backup('password', Path('backup_encrypted.btx'))"

# ♻️ Restore from encrypted backup file
restore:
	python -c "from backend.services.backup import restore_backup; from pathlib import Path; restore_backup('password', Path('backup_encrypted.btx'))"
