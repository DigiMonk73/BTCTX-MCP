"""
docs/HAND-TEST.md, the test pack's guide (#844), says what the app does: its
tables are worked out here from the reference figures and the app's own
previews and imports (hand_test_tables.py), and a stale one fails until
`make test-pack` writes it again. Every sample file is in it, every link
leads to a file, and it never lets anyone forget the install is a throwaway.
"""

import dataclasses
import json
import os
import re
from pathlib import Path

import pytest

from backend.services import outbound
from backend.tests import hand_test_tables as tables
from backend.tests.conftest import stub_daily_prices
from backend.tests.test_reference_csv_844 import (
    ROWS,
    UPDATE,
    csv_file,
    install,
    saved_figures,
    seed_ledger,
)

pytestmark = pytest.mark.xdist_group("reference_csv")

GUIDE = tables.GUIDE
PRICE = 100000.0  # the bitcoin price stands in for a real one: a real source gives other values, no other rows


def import_file(c, file: tables.ExchangeFile) -> dict:
    content = (tables.FILES_FOLDER / file.name).read_bytes()
    r = c.post("/api/import/exchange/preview", data={"mapping_id": file.mapping_id},
               files={"file": (file.name, content, "text/csv")})
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["errors"] == [], (file.name, preview["errors"])
    rows = tables.rows_to_send(preview, file.untick)
    r = c.post("/api/import/exchange/execute", json={"rows": rows})  # never a past year's question: the tests' pin
    assert r.status_code == 200, (file.name, r.text)
    assert r.json()["imported_count"] == len(rows), file.name
    return preview


def file_sections() -> str:
    """Each sample file, on a new install with one of each account (the one
    it follows imported first), its price source chosen."""
    by_name = {file.name: file for file in tables.EXCHANGE_FILES}
    said = []
    for file in tables.EXCHANGE_FILES:
        with install() as (c, _), pytest.MonkeyPatch.context() as mp:
            mp.setattr(outbound, "_current", outbound.NetworkSettings(price_source="public"))
            stub_daily_prices(mp, lambda day: PRICE)
            if file.after:
                import_file(c, by_name[file.after])
            preview = import_file(c, file)
            said.append(tables.file_section(file, preview, c.get("/api/calculations/accounts/balances").json()))
    return "\n\n".join(said)


def template_section() -> str:
    with install() as (c, _):
        template = c.get("/api/import/template").text
        preview = c.post("/api/import/preview", files=csv_file(template)).json()
        r = c.post("/api/import/execute", files=csv_file(template))
        assert r.status_code == 200, r.text
        return tables.template_section(preview, c.get("/api/calculations/accounts/balances").json())


def reference_preview_section() -> str:
    return f"{tables.csv_preview_line(ROWS, ROWS, 0)}\n- **The button:** \"Import {ROWS} Transactions\"."


@pytest.fixture(scope="module")
def sections(auth_client) -> dict[str, str]:
    figures = saved_figures()
    return {
        "accounts": tables.accounts_table(json.loads(seed_ledger.LEDGER.read_text())["accounts"]),
        "template": template_section(),
        "files": file_sections(),
        "reference-preview": reference_preview_section(),
        "figures": tables.figures_tables(figures),
    }


def test_the_guides_tables_are_up_to_date(sections):
    if os.environ.get(UPDATE):
        GUIDE.write_text(tables.replace_sections(GUIDE.read_text(), sections))
    found = tables.sections_in(GUIDE.read_text())
    stale = [name for name, body in sections.items() if found.get(name) != body.strip()]
    assert not stale, f"docs/HAND-TEST.md's {stale} are stale: `make test-pack` writes them again"


def test_left_ticked_swans_row_stops_the_import_as_the_guide_says(auth_client):
    """Its coins come from a wallet holding none: the whole file is refused, nothing saved."""
    swan = next(file for file in tables.EXCHANGE_FILES if file.untick)
    with install() as (c, _):
        with pytest.raises(AssertionError, match="Not enough BTC"):
            import_file(c, dataclasses.replace(swan, untick=()))
        assert c.get("/api/transactions").json() == []


def test_every_sample_file_is_in_the_guide():
    assert {path.name for path in tables.FILES_FOLDER.glob("*.csv")} == {f.name for f in tables.EXCHANGE_FILES}
    text = GUIDE.read_text()
    assert all(f"exchange_files/{f.name})" in text for f in tables.EXCHANGE_FILES)


def test_every_link_in_the_guide_leads_to_a_file():
    for link in re.findall(r"\]\((?!https?:|#)([^)#]+)", GUIDE.read_text()):
        assert (GUIDE.parent / link).resolve().exists(), link


def test_the_guide_and_the_testing_guide_and_the_folder_point_to_each_other():
    root = Path(__file__).resolve().parents[2]
    assert "HAND-TEST.md" in (root / "docs" / "TESTING.md").read_text()
    assert "HAND-TEST.md" in (root / "testdata" / "README.md").read_text()
    assert "reference_ledger.csv" in GUIDE.read_text()


def test_the_guide_says_a_throwaway_install_only():
    text = GUIDE.read_text()
    assert "a throwaway install only, never your records" in text.casefold()
    assert "several" not in text.casefold()  # AGENTS.md: "multiple wallets, exchanges or accounts"


def test_the_guides_box_figures_are_schedule_ds_lines():
    """The guide gives one table for both: each box's totals are its
    Schedule D line's, in every year with forms."""
    for year, data in saved_figures()["years"].items():
        lines = data["schedule_d"]["lines"]
        for box in data["report"]["form_8949_boxes"]:
            if year == "2023":
                continue  # no IRS forms for 2023: the report's table only
            line = lines[box["line"]]
            assert (float(line["proceeds"]), float(line["cost"]), float(line["gain_loss"])) == (
                box["proceeds"], box["cost"], box["gain_loss"]), (year, box["box"])
