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
# make lock         recompile the Python locks after editing a requirements.in
# make check        lint + test + smoke + audit-deps (CI adds e2e, StartOS, Docker, macOS)
# make check-fast   the pre-push gate, without pushing

PY ?= python3

.PHONY: hooks test test-fast smoke e2e preview docker-smoke lint audit-deps lock check check-fast frontend-dist

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

# The locks as they are (this machine's packages: Linux in CI, and macOS,
# where the Mac app's pyobjc packages are), then the dev tools.
audit-deps:
	$(PY) -m pip_audit --disable-pip -r backend/requirements.txt -r desktop/requirements.txt -r .github/release-tools/requirements.txt
	$(PY) -m pip_audit -r requirements-dev.txt
	cd frontend && npm audit --audit-level=high

# Each requirements.in → requirements.txt: every indirect package, with its
# hashes, for every platform and Python ≥ 3.10. Run in the file's directory, so
# the command in the lock's header is the one Dependabot re-runs there.
# backend/ first: desktop/ is held to its versions. `make lock LOCK_ARGS=--upgrade`
# also moves the indirect packages to their latest versions.
# A PY given as a relative path (.venv/bin/python) still works after the cd.
LOCK = $(if $(findstring /,$(PY)),$(abspath $(PY)),$(PY)) -m uv pip compile --quiet --universal --python-version 3.10 --generate-hashes \
	requirements.in --output-file requirements.txt $(LOCK_ARGS)
lock:
	cd backend && $(LOCK)
	cd desktop && $(LOCK)
	cd .github/release-tools && $(LOCK)

check: lint test smoke audit-deps
	@echo "✓ all checks passed"

check-fast:
	.githooks/pre-push </dev/null
