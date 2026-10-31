"""
A sale whose Form 1099-DA differs from BitcoinTX (#158), the fees BitcoinTX
can't place where a 1099-DA lists them (#551) and the transaction ID it
doesn't keep (#156): the owner chose a note over stored broker figures
(2026-10-31), so every place a user or their AI reads says what to compare
and what the IRS asks for. No figure moves.
"""

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader

from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.tests.test_using_these_forms import box, section_pages
from mcp_server.btctx_mcp.guide import LEDGER_GUIDE

ROOT = Path(__file__).parents[2]
HEADING = "If your Form 1099-DA differs"


def report(**data) -> str:
    base = {"tax_year": 2026, "tax_timezone": "America/New_York", "report_date": "2027-02-01 15:00:00",
            "period": "2026-01-01 to 2026-12-31", "irs_forms": "final"}
    pdf = generate_comprehensive_tax_report({**base, **data})
    return " ".join("\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages).split())


@pytest.mark.parametrize("letter, line", [("G", "1b"), ("H", "2"), ("J", "8b"), ("K", "9")])
def test_a_year_with_a_sale_on_a_1099da_says_what_to_compare_and_do(letter, line):
    text = report(form_8949_boxes=[box(letter, line, 10.0)])
    for words in (HEADING, "Compare each day's total, not row by row",
                  "Box H or K: the proceeds (box 1f). Box G or J: also the cost (box 1g) and short or long (box 6).",
                  "it doesn't mean before fees", "a mistake in the ledger: correct the transaction",
                  "Cost, box G or J", "Cost, box H or K", "Short or long",
                  "(h) is (d) less (e) plus (g), so it stays your correct gain",
                  "in alphabetical order", "Instructions for Form 8949"):
        assert words in text, words


@pytest.mark.parametrize("letters", [[("I", "3")], [("L", "10")], [("C", "3")], [("A", "1b")], []])
def test_a_year_with_none_on_a_1099da_has_no_such_page(letters):
    assert HEADING not in report(form_8949_boxes=[box(*b, 10.0) for b in letters])


@pytest.mark.parametrize("forms, printed", [("final", True), ("draft", True), ("none", False), ("newer", False)])
def test_it_says_the_printed_forms_cant_show_it_only_when_there_are_some(forms, printed):
    text = report(irs_forms=forms, form_8949_boxes=[box("H", "2", 10.0)])
    words = "can't be edited: redo that page on a blank Form 8949, or enter its sales in tax software"
    assert (words in text) is printed


def test_it_tells_what_to_do_with_a_fee_a_1099da_lists():
    """#551's three cases: a transfer's fee, a gift's, donation's or lost
    coins' fee, a fee listed without its withdrawal. Only the box differs."""
    text = report(form_8949_boxes=[box("H", "2", 10.0)])
    for words in ("If your Form 1099-DA lists a network fee as a sale", "a transfer's fee",
                  "a gift's, donation's or lost coins' fee", "a fee listed without its withdrawal",
                  "move its row by hand to the page of the box your form gives", "Its gain is the same"):
        assert words in text, words


@pytest.mark.parametrize("year, says", [(2025, True), (2026, True), (2027, False)])
def test_the_relief_is_named_only_for_the_years_it_covers(year, says):
    text = report(tax_year=year, form_8949_boxes=[box("H", "2", 10.0)])
    assert ("Notice 2026-20" in text) is says
    assert HEADING in text


def test_every_report_says_there_is_no_transaction_id():
    """#156, parked by the owner: the limit is told, in a year with no
    1099-DA too (a self-custody spend's ID would be its txid)."""
    for boxes in ([box("I", "3", 10.0)], [box("H", "2", 10.0)]):
        assert "BitcoinTX keeps no sale transaction ID, so column (a) prints none" in report(form_8949_boxes=boxes)
        assert '"if available"' in report(form_8949_boxes=boxes)


def test_sales_by_exchange_doesnt_say_no_form_lists_a_fee():
    """The IRS doesn't say, and a broker may list one (#551): what's certain
    is only where BitcoinTX puts it."""
    text = report(capital_gains_transactions=[{"asset": "BTC", "date_sold": "2026-07-01T03:00:00Z", "amount": 0.1}],
                  sales_by_exchange=[{"exchange": "Exchange", "sends_1099da": True, "boxes": ["H"], "rows": 1,
                                      "proceeds": 1.0, "cost": 1.0, "gain_loss": 0.0}])
    assert "BitcoinTX puts a fee on no Form 1099-DA by itself" in text
    assert "a fee is on no Form 1099-DA by itself" not in text


def test_the_first_page_of_using_these_forms_stays_one_page_and_this_is_one_more():
    boxes = [box("G", "1b", 10.0), box("L", "10", 10.0)]
    assert section_pages(irs_forms="final", form_8949_boxes=boxes)[1] == 2
    assert section_pages(irs_forms="final", form_8949_boxes=[box("L", "10", 10.0)])[1] == 1


@pytest.mark.parametrize("text", [
    pytest.param(" ".join(LEDGER_GUIDE.split()), id="the AI guide"),
    pytest.param(" ".join((ROOT / "docs/USING.md").read_text().split()), id="the user guide"),
    pytest.param(" ".join((ROOT / "README.md").read_text().split()), id="the README"),
])
def test_the_guides_tell_the_limits_too(text):
    for words in ("compare", "Form 1099-DA", "column (f)", "column (g)", "transaction ID"):
        assert words in text, words
    assert "by hand" in text
