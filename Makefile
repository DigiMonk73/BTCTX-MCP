# Testing and CI (docs/TESTING.md). Start with `make hooks` once.
#
# make hooks        install the pre-push hook (runs `make check-fast` before every push)
# make test         full hermetic Python suite (temp DB, no server, no internet)
# make test-fast    the same without the slow stress tests (~8 min)
# make smoke        the real server on a temp DB, driven end to end
# make e2e          Playwright click-through tests of every UI flow (Chromium)
# make preview      this checkout in a browser at 127.0.0.1:8777 (throwaway data)
# make site-shots   the README's and landing page's four pictures, into docs/images/
# make reference-figures  accept new figures for the reference test ledger (testdata/)
# make test-pack    the reference ledger's CSV and docs/HAND-TEST.md's tables, made again
# make prices       the hourly price history's new hours (each release's bump; online)
# make docker-smoke build the Docker image here and run CI's container checks
# make lint         Python + frontend lint (with size limits), type check, unit tests
# make audit-deps   known-vulnerability scan of Python + npm dependencies
# make lock         recompile the Python locks after editing a requirements.in
# make check        lint + test + smoke + audit-deps (CI adds e2e, StartOS, Docker, macOS)
# make check-fast   the pre-push gate, without pushing
# make sync-check   is everything on this computer also on GitHub? (--tidy: scripts/sync-check.sh)
# make catch-up-2.0 develop into the 2.0 build, or what needs the lead (ARGS=--dry-run: look only; scripts/catch-up-2.0.sh)

PY ?= python3

.PHONY: sync-check catch-up-2.0 hooks test test-fast smoke e2e preview site-shots reference-figures test-pack prices docker-smoke lint audit-deps lock check check-fast frontend-dist

hooks:
	git config core.hooksPath .githooks
	@echo "✓ pre-push hook installed (.githooks/pre-push)"

frontend-dist:
	@mkdir -p frontend/dist

test: frontend-dist
	$(PY) -m pytest -q -n auto --dist loadgroup

test-fast: frontend-dist
	$(PY) -m pytest -q -n auto --dist loadgroup -m "not slow"

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

# The four pictures of the README (docs/images/) and the landing page
# (DigiMonk73/btctx-site, img/) from this checkout's app and
# testdata/showcase_ledger.json: frontend/e2e/shots/site.ts. Into docs/images/,
# so `git status` shows which changed; the release tests take them elsewhere
# (docs/AGENT-TESTS.md, REF-1).
SITE_SHOTS_DIR ?= $(CURDIR)/docs/images
site-shots:
	cd frontend && SITE_SHOTS_DIR="$(SITE_SHOTS_DIR)" npx playwright test -c e2e/shots/site.config.ts

# After a change meant to move figures: rewrite testdata/reference_figures.json
# from the reference test ledger; the pull request shows the difference.
reference-figures: frontend-dist
	BTCTX_UPDATE_REFERENCE_FIGURES=1 $(PY) -m pytest -q backend/tests/test_seed_ledger.py -k reference_figures

# After a change to the reference test ledger, what the imports say or a sample
# file: testdata/reference_ledger.csv and docs/HAND-TEST.md's tables, from the
# app's own export and previews; the pull request shows the difference.
test-pack: frontend-dist
	BTCTX_UPDATE_TEST_PACK=1 $(PY) -m pytest -q backend/tests/test_reference_csv_844.py backend/tests/test_hand_test_guide_844.py -k "committed_csv_is_todays_export or guides_tables_are_up_to_date"

# Each release's bump pull request: add the hours since the last refresh to
# the hourly price history's manifest (backend/assets/btc_prices/), checked
# against Bitfinex and Kraken; refuses, writing nothing, on any mismatch.
prices:
	$(PY) scripts/price_history.py refresh

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
# hashes, for every platform and Python ≥ 3.11 (#546). Run in the file's directory, so
# the command in the lock's header is the one Dependabot re-runs there.
# backend/ first: desktop/ is held to its versions. `make lock LOCK_ARGS=--upgrade`
# also moves the indirect packages to their latest versions.
# A PY given as a relative path (.venv/bin/python) still works after the cd.
LOCK = $(if $(findstring /,$(PY)),$(abspath $(PY)),$(PY)) -m uv pip compile --quiet --universal --python-version 3.11 --generate-hashes \
	requirements.in --output-file requirements.txt $(LOCK_ARGS)
lock:
	cd backend && $(LOCK)
	cd desktop && $(LOCK)
	cd .github/release-tools && $(LOCK)

check: lint test smoke audit-deps
	@echo "✓ all checks passed"

check-fast:
	.githooks/pre-push </dev/null

sync-check:
	scripts/sync-check.sh

catch-up-2.0:
	scripts/catch-up-2.0.sh $(ARGS)
