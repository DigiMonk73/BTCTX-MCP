"""
One snapshot of everything BitcoinTX produces, for scripts/equivalence_check.py.

Imported only after equivalence_check.py has put the checkout under test
first on sys.path and pointed the database, frontend and data folders at a
temp directory: the code below is that checkout's, on throwaway data.
"""

import asyncio
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import re
import shutil
import time
from datetime import date
from pathlib import Path

import httpx
from fastapi.testclient import TestClient
from mcp import Client
from pypdf import PdfReader
from reportlab import rl_config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from backend.database import get_db
from backend.main import app
from backend.routers import reports as reports_router
from backend.services import ai_key, bitcoin, first_run, login_throttle, outbound, price_history
from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.reporting_core import generate_report_data
from backend.services.transaction import recalculate_all_transactions
from backend.tests.conftest import default_login, init_test_db, price_finder
from backend.tests.test_river_import import SYNTHETIC_ROWS, river_csv
from backend.version import app_version
from btctx_mcp import server as mcp_server
from btctx_mcp.client import BtctxClient

import equivalence_inputs as inputs
from equivalence_ledgers_1x import GOLDEN_LEDGER, SeededDraws, draw_ledger, reference_rows_1x

# This checkout's, for both sides: a release's worktree may have no testdata/
REFERENCE_LEDGER = Path(__file__).resolve().parents[1] / "testdata" / "reference_ledger.json"
RANDOM_LEDGERS = 40
BENCH_TRANSACTIONS = 2000
BENCH_RUNS = 9

# Save and edit times, and hashes made from random salts.
VOLATILE_KEYS = {"created_at", "updated_at", "password_hash"}
# The backup copy's name and time.
VOLATILE_MCP_KEYS = {"file", "created"}
# Hashes of the AI key, and of the login sessions each run opens anew.
VOLATILE_SETTINGS = ("key_sha256", "open_sessions")
# The rows from before 0.9.2 (5.13, from 2.0), and which BitcoinTX last
# recalculated the ledger (5.8, from 2.0's B6b): a ledger 1.x never wrote
# them in.
UNCOMPARED_SETTINGS = ("accounts_old_rows", "recalculated_by")
# "This tax year" as backend/tests/conftest.py pins it (its PINNED_TAX_YEAR,
# which the side compared with may lack)
TESTS_TAX_YEAR = 2009

# The complete tax report prints the moment it was made: "Date: <time>"
# up to 1.2.4, a "GENERATED" line "<time> UTC" from 1.2.5.
REPORT_MOMENT = re.compile(r"^(Date: )?\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}( UTC)?$", re.M)


def masked_report_pages(pages: list[str]) -> list[str]:
    """The report's page texts with the moment it was made replaced by <now>."""
    return [REPORT_MOMENT.sub(r"\1<now>\2", page) for page in pages]


def take(out: Path, work: Path, bench: bool) -> None:
    """Write the snapshot of this checkout to `out`, one JSON file per ledger."""
    out.mkdir(parents=True, exist_ok=True)
    _shut_out_the_world(work)
    rl_config.invariant = 1  # ReportLab PDFs without creation time or random ids
    openapi = app.openapi()
    _write(out / "meta.json", {
        "openapi": _without_descriptions(openapi),
        "openapi_descriptions": _descriptions(openapi),
        "mcp_tools": asyncio.run(_mcp_tool_list()),
        "csv_instructions_pdf": _csv_instructions_pdf(work),
    })
    for name, zone, txs in _ledgers():
        _write(out / f"{name}.json", _ledger_snapshot(work, name, zone, txs))
    _write(out / "bad_inputs.json", _bad_input_snapshot(work))
    if bench:
        _write(out / "bench.json", _bench(work))


def _without_descriptions(value):
    if isinstance(value, dict):
        return {k: _without_descriptions(v) for k, v in value.items() if k != "description"}
    if isinstance(value, list):
        return [_without_descriptions(v) for v in value]
    return value


def _descriptions(value, path="") -> dict:
    """Every description in the API schema, by where it is."""
    found = {}
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "description" and isinstance(item, str):
                found[path] = item
            else:
                found.update(_descriptions(item, f"{path}/{key}"))
    elif isinstance(value, list):
        for i, item in enumerate(value):
            found.update(_descriptions(item, f"{path}[{i}]"))
    return found


def _write(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=1, default=str, ensure_ascii=False) + "\n")


def daily_usd(day: date) -> float:
    """A different, repeatable price each day, so a value taken on the wrong
    day shows."""
    return 20000 + (day.toordinal() % 1000) * 41.37


def _shut_out_the_world(work: Path) -> None:
    """Stubbed prices, the public price source chosen, first-run files in the
    temp folder: as the test suite runs, with nothing sent anywhere."""
    async def current_price():
        return {"USD": 60000.0}

    price_history.find_prices = price_finder(daily_usd)
    bitcoin.get_current_price = current_price
    _no_hourly_prices()
    (work / "data").mkdir(exist_ok=True)
    first_run.DATA_DIR = str(work / "data")
    outbound._current = outbound.NetworkSettings(price_source="public")
    mcp_server.connector_version = app_version
    pin_tax_year()


def pin_tax_year() -> None:
    """"This tax year" is 2009, before every ledger's, as the backend tests
    pin it (2.0 plan 5.15): 2.0's past-year warning (5.8) never asks, so an
    in-process write saves as it did before the warning. A side without
    the clock (services/tax_time.current_tax_year: 1.x, or 2.0 before it)
    gets none."""
    from backend.services import tax_time

    if hasattr(tax_time, "current_tax_year"):
        tax_time.current_tax_year = lambda tz: TESTS_TAX_YEAR


def _no_hourly_prices() -> None:
    """No hourly price and no download of the year files (#144): values are
    priced at the stubbed day's price. A release before hourly prices has
    neither (the snapshot code is this checkout's, the app the release's)."""
    try:
        from backend.services import hourly_prices
    except ImportError:
        return

    async def no_hours(hour, files_end, stored):
        return {}

    hourly_prices.find_hours = no_hours
    hourly_prices.start_download = lambda: False


def _ledgers():
    """(name, tax timezone, API payloads) for each ledger in the snapshot."""
    yield "golden", inputs.GOLDEN_ZONE, GOLDEN_LEDGER
    yield "reference", "UTC", reference_rows_1x(REFERENCE_LEDGER)
    for seed in range(RANDOM_LEDGERS):
        txs, _ = draw_ledger(SeededDraws(seed), max_ops=25)
        yield f"random_{seed:02d}", inputs.RANDOM_ZONES[seed % len(inputs.RANDOM_ZONES)], txs


class Instance:
    """The app on a fresh database of its own, logged in."""

    def __init__(self, work: Path, name: str, zone: str = "UTC"):
        # The baseline is kept by today's date in these zones only (#630)
        assert zone in inputs.ZONES, f"{zone} isn't in equivalence_inputs.ZONES"
        self.path = work / f"{name}.db"
        self.engine = create_engine(f"sqlite:///{self.path}", connect_args={"check_same_thread": False})
        init_test_db(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        app.dependency_overrides[get_db] = self._session
        price_history.reset_state()
        login_throttle.reset()
        self.client = TestClient(app, raise_server_exceptions=False)  # a crash is an answer too
        assert self.client.post("/api/login", json=default_login()).status_code == 200
        assert self.client.put("/api/settings/tax-timezone", json={"timezone": zone, "chosen": True}).status_code == 200

    def _session(self):
        db = self.Session()
        try:
            yield db
        finally:
            db.close()

    @contextlib.contextmanager
    def trial(self):
        """Whatever happens inside is undone: the database file is put back."""
        saved = self.path.with_suffix(".saved")
        self.engine.dispose()
        shutil.copyfile(self.path, saved)
        try:
            yield
        finally:
            self.engine.dispose()
            shutil.copyfile(saved, self.path)
            price_history.reset_state()

    def enter(self, txs) -> list:
        return [_status(self.client.post("/api/transactions", json=tx)) for tx in txs]


def _status(response) -> list:
    """Status and, for a refusal, its message."""
    if response.status_code < 400:
        return [response.status_code]
    return [response.status_code, response.text]


def answer(response) -> dict:
    """A response as the snapshot keeps it: status, and its JSON, text or PDF."""
    kind = response.headers.get("content-type", "")
    if "json" in kind:
        body = _without_volatile(response.json())
    elif "pdf" in kind:
        body = pdf_summary(response.content)
    else:
        body = response.text
    return {"status": response.status_code, "body": body}


def _without_volatile(value):
    if isinstance(value, dict):
        return {k: _without_volatile(v) for k, v in value.items() if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [_without_volatile(v) for v in value]
    return value


def pdf_summary(pdf: bytes) -> dict:
    return {
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "pages": [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages],
    }


def _ledger_snapshot(work: Path, name: str, zone: str, txs) -> dict:
    instance = Instance(work, name, zone)
    snap = {"entered": instance.enter(txs)}
    snap["database"] = database_rows(instance.engine)
    snap["api"] = _api_answers(instance.client)
    snap["reports"] = {year: _year_reports(instance, year) for year in _report_years(instance.client)}
    snap["csv"] = _csv_answers(instance.client)
    snap["mcp"] = asyncio.run(_mcp_session(instance))
    with instance.trial():
        snap["river"] = _river_import(instance.client)
    with instance.trial():
        snap["entries"] = _entry_import(instance.client)
    with instance.trial():
        snap["recalculated"] = _recalculated(instance)
    return snap


def database_rows(engine) -> dict:
    """Every row of every table, in id order, without volatile columns."""
    tables = {}
    with engine.connect() as con:
        for table in sorted(inspect(engine).get_table_names()):
            rows = con.execute(text(f'SELECT * FROM "{table}" ORDER BY rowid')).mappings().all()
            tables[table] = [_stable_row(table, row) for row in rows
                             if not (table == "app_settings" and row["key"] in UNCOMPARED_SETTINGS)]
    return tables


def _stable_row(table: str, row) -> dict:
    kept = {k: v for k, v in row.items() if k not in VOLATILE_KEYS}
    if table == "app_settings" and any(word in str(kept.get("key")) for word in VOLATILE_SETTINGS):
        kept["value"] = "<volatile>"
    return kept


def _api_answers(client) -> dict:
    paths = [
        "/api/transactions",
        "/api/calculations/accounts/balances",
        "/api/calculations/average-cost-basis",
        "/api/calculations/gains-and-losses",
        "/api/review",
        "/api/debug/lots",
        "/api/debug/disposals",
        "/api/debug/ledger-entries",
        "/api/reports/years",
        "/api/accounts/",
    ]
    answers = {path: answer(client.get(path)) for path in paths}
    for tx in answers["/api/transactions"]["body"]:
        path = f"/api/transactions/{tx['id']}"
        answers[path] = answer(client.get(path))
    return answers


def _report_years(client) -> list:
    return sorted(client.get("/api/reports/years").json()["ledger_years"])


def _year_reports(instance: Instance, year: int) -> dict:
    client = instance.client
    reports = {"irs": _irs_reports(client, year)}
    complete = answer(client.get("/api/reports/complete_tax_report", params={"year": year}))
    if isinstance(complete["body"], dict):
        del complete["body"]["sha256"]  # it holds the moment the report was made
        complete["body"]["pages"] = masked_report_pages(complete["body"]["pages"])
    reports["complete"] = complete
    reports["complete_data_and_pdf"] = _complete_report(instance, year)
    for fmt in ("pdf", "csv"):
        params = {"year": year, "format": fmt}
        reports[f"history_{fmt}"] = answer(client.get("/api/reports/simple_transaction_history", params=params))
    return reports


def _irs_reports(client, year: int) -> dict:
    """The IRS PDF and the field values of each sheet, in the order filled."""
    sheets = []
    fill = reports_router.fill_pdf_form

    def recording_fill(template, fields, *args, **kwargs):
        sheets.append([Path(template).name, [[k, v] for k, v in fields.items()]])
        return fill(template, fields, *args, **kwargs)

    reports_router.fill_pdf_form = recording_fill
    try:
        response = answer(client.get("/api/reports/irs_reports", params={"year": year}))
    finally:
        reports_router.fill_pdf_form = fill
    return {"response": response, "sheets": sheets}


def _complete_report(instance: Instance, year: int) -> dict:
    """The complete report's data, and its PDF made from that data with the
    moment fixed, so the PDF's bytes can be compared."""
    with instance.Session() as db:
        try:
            data = generate_report_data(db, year)
        except Exception as exc:  # a refusal is part of the snapshot
            return {"error": f"{type(exc).__name__}: {getattr(exc, 'detail', exc)}"}
        db.commit()
    data["report_date"] = "<now>"
    return {"data": json.loads(json.dumps(data, default=str)), "pdf": pdf_summary(generate_comprehensive_tax_report(data))}


def _csv_answers(client) -> dict:
    export = client.get("/api/backup/csv")
    return {
        "export": answer(export),
        "template": answer(client.get("/api/import/template")),
        "status": answer(client.get("/api/import/status")),
        "preview_of_export": _csv_preview(client, export.content),
    }


def _csv_preview(client, content: bytes) -> dict:
    return answer(client.post("/api/import/preview", files={"file": ("import.csv", content, "text/csv")}))


def _river_import(client) -> dict:
    rows = list(SYNTHETIC_ROWS) + list(inputs.RIVER_BAD_ROWS)
    files = {"file": ("river.csv", io.BytesIO(river_csv(rows)), "text/csv")}
    preview = answer(client.post("/api/import/river/preview", files=files))
    ok = [p for p in preview["body"].get("proposals", []) if p.get("status") == "new"] \
        if isinstance(preview["body"], dict) else []
    execute = answer(client.post("/api/import/river/execute", json={"rows": ok}))
    return {"preview": preview, "execute": execute, "after": answer(client.get("/api/transactions"))}


def _entry_import(client) -> dict:
    rows = list(inputs.ENTRY_BASE_ROWS)
    changed = []
    for base in inputs.ENTRY_BASE_ROWS:
        for field, value in inputs.ENTRY_CHANGES:
            changed.append({**base, field: value})
    return {
        "preview_valid": answer(client.post("/api/import/entries/preview", json={"rows": rows})),
        "preview_changed": [
            answer(client.post("/api/import/entries/preview", json={"rows": [row]})) for row in changed
        ],
        "execute_valid": answer(client.post("/api/import/entries/execute", json={"rows": rows})),
        "after": answer(client.get("/api/transactions")),
    }


def _recalculated(instance: Instance) -> dict:
    """Recalculating the whole ledger changes nothing, through the API and
    the CLI's function."""
    response = answer(instance.client.post("/api/transactions/recalculate"))
    with instance.Session() as db:
        recalculate_all_transactions(db)
        db.commit()
    return {"response": response, "database": database_rows(instance.engine)}


# MCP connector
async def _mcp_tool_list() -> list:
    async with Client(mcp_server.mcp) as client:
        tools = (await client.list_tools()).tools
    return [tool.model_dump(mode="json") for tool in tools]


async def _mcp_session(instance: Instance) -> list:
    """Every tool, as the connector's tests call them, against this ledger;
    what they change is undone afterwards."""
    with instance.Session() as db:
        ai_key.set_access(db, True)
        key = ai_key.create_key(db)
    btctx = BtctxClient(base_url="http://testserver", ai_key=key, transport=httpx.ASGITransport(app=app))
    mcp_server.set_client(btctx)
    mcp_server._version = {"checked": False, "notice": None}
    calls = []
    try:
        async with Client(mcp_server.mcp) as client:
            with instance.trial():
                for name, args in _mcp_calls(instance):
                    calls.append([name, args, await _mcp_call(client, name, args)])
    finally:
        mcp_server.set_client(None)
        await btctx.aclose()
    return calls


def _mcp_calls(instance: Instance):
    yield "get_ledger_guide", {}
    yield "get_portfolio", {}
    for filters in inputs.MCP_LIST_FILTERS:
        yield "list_transactions", filters
    yield "get_btc_price", {"date": "2024-05-01"}
    yield "review_ledger", {}
    yield "preview_transactions", {"transactions": inputs.ENTRY_BASE_ROWS}
    yield "add_transactions", {"transactions": inputs.ENTRY_BASE_ROWS[:2]}
    newest = max(tx["id"] for tx in instance.client.get("/api/transactions").json())
    yield "update_transaction", {"transaction_id": newest, "amount": "0.002"}
    yield "update_transaction", {"transaction_id": newest, "type": "Sell"}
    yield "update_transaction", {"transaction_id": 999999, "amount": "1"}
    yield "delete_transaction", {"transaction_id": newest}
    yield "recalculate_ledger", {}
    yield "backup_ledger", {}
    yield "get_portfolio", {}


async def _mcp_call(client, name: str, args: dict) -> list:
    result = await client.call_tool(name, args)
    text_ = "".join(getattr(c, "text", "") for c in result.content)
    try:
        body = _without_volatile(json.loads(text_))
    except ValueError:
        body = text_
    if name == "backup_ledger" and isinstance(body, dict):
        body = {k: "<volatile>" if k in VOLATILE_MCP_KEYS else v for k, v in body.items()}
    return [bool(result.is_error), body]


# Bad inputs
def _bad_input_snapshot(work: Path) -> dict:
    instance = Instance(work, "bad_inputs", inputs.GOLDEN_ZONE)
    instance.enter(GOLDEN_LEDGER)
    snap = {
        "create": _api_trials(instance, "POST"),
        "edit": _api_trials(instance, "PUT"),
        "delete": _delete_trials(instance),
    }
    empty = Instance(work, "bad_csv")
    snap["csv_rows"] = _csv_row_trials(empty.client)
    snap["csv_files"] = {
        name: _csv_preview(empty.client, content if isinstance(content, bytes) else content.encode())
        for name, content in inputs.CSV_BAD_FILES.items()
    }
    return snap


def _changed(payload: dict, field: str, value) -> dict:
    changed = dict(payload)
    if value is None:
        changed.pop(field, None)
    else:
        changed[field] = value
    return changed


def _api_trials(instance: Instance, method: str) -> list:
    """Each base payload with each change, created (POST) or written over
    the golden ledger's transaction of the same type (PUT); undone after."""
    ids = {tx["type"]: tx["id"] for tx in instance.client.get("/api/transactions").json()}
    results = []
    for name, payload in inputs.API_PAYLOADS.items():
        for field, value in inputs.API_CHANGES:
            body = _changed(payload, field, value)
            with instance.trial():
                if method == "POST":
                    response = instance.client.post("/api/transactions", json=body)
                else:
                    response = instance.client.put(f"/api/transactions/{ids[payload['type']]}", json=body)
                results.append([name, field, value, answer(response)])
    return results


def _delete_trials(instance: Instance) -> list:
    results = []
    for tx in instance.client.get("/api/transactions").json():
        with instance.trial():
            results.append([tx["id"], _status(instance.client.delete(f"/api/transactions/{tx['id']}"))])
    return results


def _csv_row_trials(client) -> list:
    """Each base row alone, then with each value in each column."""
    results = []
    for name, base in inputs.CSV_BASE_ROWS.items():
        results.append([name, None, None, _csv_preview(client, _csv_file([base]))])
        for column, values in inputs.CSV_CHANGES.items():
            for value in values:
                row = {**base, column: value}
                results.append([name, column, value, _csv_preview(client, _csv_file([row]))])
    return results


def _csv_file(rows: list) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=inputs.CSV_COLUMNS, restval="", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


# The CSV instructions PDF and the recalculation time
def _csv_instructions_pdf(work: Path) -> dict:
    """The script run from a copy of itself in the temp folder, so its PDF
    lands there and the committed one is untouched."""
    copy = work / "scripts" / "generate_csv_instructions_pdf.py"
    copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile("backend/scripts/generate_csv_instructions_pdf.py", copy)
    spec = importlib.util.spec_from_file_location("csv_instructions", copy)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with contextlib.redirect_stdout(io.StringIO()):  # it prints where the PDF went
        path = module.generate_csv_instructions_pdf()
    return pdf_summary(Path(path).read_bytes())


def _bench(work: Path) -> dict:
    """The fastest of several full recalculations of a large ledger (the
    least disturbed by whatever else the machine is doing)."""
    overrides = {
        "ops": lambda rng: BENCH_TRANSACTIONS,
        "gap_days": lambda rng: 0,
        "minutes": lambda rng: rng.randint(60, 720),
    }
    txs, _ = draw_ledger(SeededDraws(0, overrides), max_ops=BENCH_TRANSACTIONS)
    instance = Instance(work, "bench")
    assert all(status == [200] for status in instance.enter(txs))
    runs = []
    with instance.Session() as db:
        for _ in range(BENCH_RUNS):
            start = time.perf_counter()
            recalculate_all_transactions(db)
            runs.append(time.perf_counter() - start)
            db.rollback()
    return {"transactions": len(txs), "runs": runs, "fastest": min(runs)}
