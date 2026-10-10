"""
The Complete Tax Report's "Using these forms" page (#79): for whoever files
the return, what BitcoinTX fills on Form 8949 and Schedule D and what it
leaves blank on purpose (the owner's decision: never a carryover, nor the
lines that depend on the rest of the return), the Bitcoin-only figures for
lines 7, 15 and 16 with line 21's rule, and a note while the year isn't over.
"""

from io import BytesIO

import pytest
from pypdf import PdfReader

from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report


def report_text(**data) -> str:
    base = {"tax_year": 2025, "tax_timezone": "America/New_York", "report_date": "2026-02-01 15:00:00",
            "period": "2025-01-01 to 2025-12-31", "irs_forms": "final", "form_8949_boxes": []}
    pdf = generate_comprehensive_tax_report({**base, **data})
    text = "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)
    return " ".join(text[text.rindex("6. Using these forms"):text.rindex("7. Notes")].split())


def cover_text(**data) -> str:
    base = {"tax_year": 2025, "tax_timezone": "America/New_York", "period": "2025-01-01 to 2025-12-31"}
    pdf = generate_comprehensive_tax_report({**base, **data})
    return " ".join((PdfReader(BytesIO(pdf)).pages[0].extract_text() or "").split())


def box(letter: str, line: str, gain: float) -> dict:
    return {"box": letter, "line": line, "rows": 1, "proceeds": 1000.0, "cost": 1000.0 - gain, "gain_loss": gain}


def test_it_says_what_is_filled_and_what_is_left_blank():
    text = report_text(form_8949_boxes=[box("H", "2", -1000.0), box("L", "10", 7472.70)])
    assert "This year's boxes: H and L (what each holds: section 1)." in text
    assert "Schedule D: lines 2 and 10, each the total of its box's Form 8949 pages" in text
    assert "a page or more per box" in text
    for blank in ("lines 1a and 8a: every sale goes on Form 8949", "lines 6 and 14, the loss carryovers",
                  "Lines 4, 5, 11, 12 and 13", "Lines 7, 15, 16 and 21, and the rest of Part III",
                  "The qualified opportunity fund question at the top of Schedule D: answer it."):
        assert blank in text
    assert "Write the name and social security number on every Form 8949 page and on Schedule D" in text
    assert "Print single-sided" in text
    assert "one self-custody wallet and one exchange account" in text and "Rev. Proc. 2024-28" in text
    assert "(IRC §1015)" in text and "adjusted by hand (its basis and holding period)" in text
    assert "BitcoinTX is software, not tax, legal or financial advice." in text


def test_the_bitcoin_only_figures_add_up_the_lines():
    text = report_text(form_8949_boxes=[box("H", "2", -1000.0), box("I", "3", 200.0), box("L", "10", 7472.70)])
    assert "7 Net short-term gain (loss) ($800.00)" in text
    assert "15 Net long-term gain (loss) $7,472.70" in text
    assert "16 Lines 7 and 15 combined $6,672.70" in text
    assert "Line 16 isn't a loss, so line 21 doesn't apply." in text


def test_a_net_loss_gives_line_21s_rule():
    text = report_text(form_8949_boxes=[box("K", "9", -5000.0)])
    assert "16 Lines 7 and 15 combined ($5,000.00)" in text
    assert "line 21 is the smaller of the loss ($5,000.00) and $3,000, or $1,500 if married filing separately" in text
    assert "a loss not deducted may carry over to next year (the Capital Loss Carryover Worksheet)" in text
    assert "Schedule D: line 9, the total of its box's Form 8949 pages" in text


def test_a_report_made_before_the_year_ends_says_so():
    """Dates in the tax timezone: 04:30 UTC on January 1 is still December 31
    in New York."""
    note = "The year isn't over yet: this report was made on 12/31/2025"
    assert note in report_text(report_date="2025-12-31 23:00:00")
    assert "YEAR NOT OVER Made 12/31/2025: figures to that day only" in cover_text(report_date="2025-12-31 23:00:00")
    assert note in report_text(report_date="2026-01-01 04:30:00")
    assert "The year isn't over yet" not in report_text(report_date="2026-01-01 05:30:00")


@pytest.mark.parametrize("zone", ["America/Indiana/Indianapolis", "America/Los_Angeles", "UTC"])
def test_the_cover_keeps_the_contents_with_the_year_not_over(zone):
    """Re-check of #108: a two-line cover row pushed the contents' last entry
    onto a second page when a long timezone name wrapped its own row."""
    text = cover_text(tax_timezone=zone, report_date="2025-10-10 15:00:00")
    assert "YEAR NOT OVER" in text and "7. Notes" in text


@pytest.mark.parametrize("forms, expected", [
    ("draft", "The 2025 forms are the IRS's drafts, marked DRAFT — DO NOT FILE"),
    ("none", "BitcoinTX has no IRS forms for 2025, so it fills none."),
    ("newer", "BitcoinTX has no IRS forms for 2025 yet, so it fills none: a newer BitcoinTX may have them."),
])
def test_it_says_when_the_forms_are_drafts_or_missing(forms, expected):
    text = report_text(irs_forms=forms, form_8949_boxes=[box("H", "2", -1000.0)])
    assert expected in text
    if forms != "draft":
        # Nothing filled: the Form 8949 instructions' attached statement, never totals alone
        assert "Form 8949: every Bitcoin disposal" not in text and "Fill Form 8949 from section 2's list" in text
        assert 'enter each box\'s totals on Form 8949: "see attached statement" in column (a), (b) and (c) ' \
               "blank, code M in column (f) (Form 8949 instructions, Exception 2)" in text


@pytest.mark.parametrize("year, note", [(2001, "BitcoinTX has no IRS forms for 2001, so it fills none."),
                                        (2030, "BitcoinTX has no IRS forms for 2030 yet, so it fills none")])
def test_the_route_says_when_a_year_has_no_forms(auth_client, year, note):
    """Before BitcoinTX's first forms, or after its newest ones (no draft)."""
    r = auth_client.get("/api/reports/complete_tax_report", params={"year": year})
    assert r.status_code == 200
    assert note in " ".join("\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(r.content)).pages).split())


def test_a_report_made_without_the_forms_choice_says_nothing_of_it():
    """generate_comprehensive_tax_report called without irs_forms (scripts/
    equivalence_snapshot.py) neither says the forms are missing nor drafts."""
    pdf = generate_comprehensive_tax_report({"tax_year": 2025, "report_date": "2026-02-01 15:00:00",
                                             "form_8949_boxes": [box("H", "2", -1000.0)]})
    text = " ".join("\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages).split())
    assert "Form 8949: every Bitcoin disposal of 2025" in text
    assert "no IRS forms" not in text and "drafts" not in text
