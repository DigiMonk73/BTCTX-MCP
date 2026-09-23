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
