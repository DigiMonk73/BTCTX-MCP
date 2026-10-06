# Testing and CI (docs/TESTING.md). Start with `make hooks` once.
#
# make hooks        install the pre-push hook (runs `make check-fast` before every push)
# make test         full hermetic Python suite (temp DB, no server, no internet)
# make test-fast    the same without the slow stress tests (~1 min)
# make smoke        the real server on a temp DB, driven end to end
# make e2e          Playwright click-through tests of every UI flow (Chromium)
# make preview      this checkout in a browser at 127.0.0.1:8777 (throwaway data)
# make docker-smoke build the Docker image here and run CI's container checks
# make lint         Python + frontend lint (with size limits), type check, unit tests
# make audit-deps   known-vulnerability scan of Python + npm dependencies
# make check        lint + test + smoke + audit-deps (CI adds e2e, StartOS, Docker, macOS)
# make check-fast   the pre-push gate, without pushing

PY ?= python3

.PHONY: hooks test test-fast smoke e2e preview docker-smoke lint audit-deps check check-fast frontend-dist

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

# Click-through tests: builds frontend/dist, a fresh server per test.
# Uses .venv/bin/python if present, else BTCTX_PYTHON, else python3.
e2e:
	cd frontend && npx playwright test --project=chicago --project=tokyo

# This checkout on a throwaway database with offline prices; login in
# scripts/smoke_test.py (SMOKE_USER). Ctrl-C stops it.
preview:
	$(PY) scripts/preview.py

docker-smoke:
	scripts/docker_smoke.sh

lint:
	$(PY) -m ruff check .
	cd frontend && npm run lint && npx tsc -b && npm test

audit-deps:
	$(PY) -m pip_audit -r backend/requirements.txt -r requirements-dev.txt
	cd frontend && npm audit --audit-level=high

check: lint test smoke audit-deps
	@echo "✓ all checks passed"

check-fast:
	.githooks/pre-push </dev/null
