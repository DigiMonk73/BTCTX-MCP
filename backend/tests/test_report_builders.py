"""
The report builders on inputs the ledger tests rarely produce: every
section of the complete tax report (empty and filled, rows of other assets
left out, dates that aren't ISO 8601, values not priced), the transaction
history of a year without transactions, and the Form 8949 page guards.
They pin what the builders print, so no refactoring can change it unseen.
"""

import io
import re
from decimal import Decimal

import pytest
from pypdf import PdfReader

from backend.services.reports.complete_tax_report import generate_comprehensive_tax_report
from backend.services.reports.form_8949 import Form8949Row, map_8949_rows_to_field_data

REPORT = {
    "tax_year": 2024,
    "report_date": "2025-01-05 10:00:00",
    "period": "2024-01-01 to 2024-12-31",
    "tax_timezone": "America/New_York",
    "start_of_year_balances": [{"quantity": 0.25, "avg_cost_basis": 30000.0, "value": None}],
    "capital_gains_summary": {
        "short_term": {"proceeds": 1500.5, "basis": 1000.0, "gain": 500.5, "profits": 600.0, "losses": 99.5},
        "number_of_disposals": 3,
    },
    "income_transactions": [
        {"date": "2024-03-01T04:30:00Z", "asset": "BTC", "amount": 0.01, "value_usd": 600.0, "type": "Income",
         "description": "salary"},
        {"date": "2024-03-02T12:00:00", "asset": "USD", "amount": 25.0, "value_usd": 25.0, "type": "Interest",
         "description": ""},
        {"date": "", "asset": "ETH", "amount": 1.0, "value_usd": 9.0, "type": "Reward", "description": "left out"},
    ],
    "end_of_year_balances": [
        {"asset": "BTC (Bitcoin)", "account": "Wallet", "acquired": "2024-01-15T12:00:00Z", "quantity": 0.5,
         "cost": 20000.0, "value": None, "description": "No BTC price for 2024-12-31: not priced"},
        {"asset": "USD (Bank)", "quantity": 10.0, "cost": 10.0, "value": 10.0, "description": "left out"},
        {"asset": "Total", "quantity": 0.5, "cost": 20000.0, "value": None, "description": ""},
    ],
    "form_8949_boxes": [
        {"box": "F", "line": "10", "rows": 1, "proceeds": 6000.0, "cost": 3000.0, "gain_loss": 3000.0},
    ],
    "capital_gains_transactions": [
        {"asset": "BTC", "date_sold": "2024-07-01T03:00:00Z", "date_acquired": "not a date", "amount": 0.1,
         "cost": 3000.0, "proceeds": 6000.0, "gain_loss": 3000.0, "holding_period": "LONG", "kind": "Sale",
         "box": "F"},
        {"asset": "ETH", "date_sold": "2024-07-01T03:00:00Z", "date_acquired": "", "amount": 1, "cost": 1,
         "proceeds": 1, "gain_loss": 0, "holding_period": "left out"},
    ],
    "gifts_donations_lost": [
        {"date": "2024-08-01T12:00:00Z", "asset": "BTC", "amount": 0.02, "proceeds_usd": 0.0, "fmv_usd": 1200.0,
         "type": "Gift", "lots_by_term": [{"term": "LONG", "btc": 0.02, "cost_basis": 500.0}]},
        {"date": "2024-08-02T12:00:00Z", "asset": "BTC", "amount": 0.03, "proceeds_usd": 0.0, "fmv_usd": None,
         "type": "Lost"},
    ],
}

EMPTY_REPORT = {"tax_year": 2023, "report_date": "2024-01-02 03:04:05", "period": "2023-01-01 to 2023-12-31"}


def pdf_text(pdf: bytes) -> str:
    return " ".join(" ".join(page.extract_text().split()) for page in PdfReader(io.BytesIO(pdf)).pages)


def test_complete_report_sections():
    text = pdf_text(generate_comprehensive_tax_report(REPORT))
    for expected in (
        # The cover: the year's key figures and how the report was made
        "TAX YEAR 2024 Bitcoin Tax Report Capital gains, income and holdings, January 1 to December 31, 2024",
        "NET CAPITAL GAIN (LOSS) $500.50 Short-term $500.50 · Long-term $0.00 INCOME $600.00",
        "BITCOIN HELD AT YEAR END 0.50000000 BTC Cost basis $20,000.00 VALUE AT YEAR END not priced",
        "GENERATED 2025-01-05 10:00:00 UTC",
        # The summary; a loss in parentheses, as on the IRS forms
        "Total 1 $1,500.50 $1,000.00 $600.00 ($99.50) $500.50",
        "F Long-term, not on a Form 1099-B 10 1 $6,000.00 $3,000.00 $3,000.00",
        # Income rows are BTC: a USD row (none is ever built) stays out of the BTC column
        "Income 1 0.01000000 $600.00 Reward 0 0.00000000 $0.00 Interest 0 0.00000000 $0.00 "
        "Total 1 0.01000000 $600.00",
        "January 1, 2024 0.25000000 $7,500.00 $30,000.00 not priced December 31, 2024 0.50000000 $20,000.00 "
        "$40,000.00 not priced No BTC price is stored for 2024-01-01",
        # The detail: dates in the tax timezone; one that isn't ISO 8601 is printed as it is
        "06/30/2024 not a date Sale F Long 0.10000000 $6,000.00 $3,000.00 $3,000.00",
        "02/29/2024 Income 0.01000000 $600.00 Total 0.01000000 $600.00",
        # An unvalued gift is never counted as $0 (review of #63); each row's
        # term and cost basis from its lots (#160), blank in an older report's
        "08/01/2024 Gift Long 0.02000000 $1,200.00 $500.00 08/02/2024 Lost 0.03000000 not given "
        "Total 0.05000000 $1,200.00 + 1 not given $500.00",
        # What each kind means for the return (#160)
        "Income paid for your work as an independent contractor goes on Schedule C, at the same value, and is "
        "self-employment income (Schedule SE).",
        "Gifts: if all you gave one person other than your spouse in 2024 adds up to more than $18,000, you "
        "generally need to file a gift tax return, Form 709.",
        "Lost coins: BitcoinTX records no loss for them. A theft or scam loss in an investment made for profit "
        "may be deductible on Form 4684, Section B (not Form 8949), up to the coins' cost basis: ask your tax "
        "preparer.",
        "Form 1040's digital asset question: answer Yes, for the bitcoin disposed of (section 2), received "
        "(section 3) and given (section 4).",
        "Wallet 1 0.50000000 $20,000.00 not priced Total 1 0.50000000 $20,000.00 not priced "
        "No BTC price for 2024-12-31: not priced",
        "Average cost: $40,000.00 per BTC",  # after a page break since #160's notes
        "01/15/2024 Wallet 0.50000000 $20,000.00 not priced Total 0.50000000 $20,000.00 not priced",
        "in the tax timezone (America/New_York)",
    ):
        assert expected in text, expected
    assert "left out" not in text and "USD (Bank)" not in text and not re.search(r"\bETH\b", text)
    assert "-0.00" not in text
    assert "Donations:" not in text and "Term Both" not in text  # no donation, none of both terms
    assert "which time zone sets your dates" not in text  # box F: no broker's form


def donation(date: str, *parts: tuple[str, float, float], fmv: float | None = 3000.0) -> dict:
    return {"date": date, "asset": "BTC", "amount": sum(p[1] for p in parts), "proceeds_usd": 0.0, "fmv_usd": fmv,
            "type": "Donation", "lots_by_term": [{"term": t, "btc": b, "cost_basis": c} for t, b, c in parts]}


def test_a_donation_shows_its_basis_its_term_and_the_deduction_rules():
    """#160: a donation's deduction depends on how long its coins were held
    and their cost basis; one of both terms is split, as each part follows
    its own rule. The appraisal and Form 8283 come with it."""
    gifts = [donation("2024-05-01T12:00:00Z", ("SHORT", 0.01, 900.0)),
             donation("2024-06-01T12:00:00Z", ("LONG", 0.02, 400.0), ("SHORT", 0.01, 950.0))]
    text = pdf_text(generate_comprehensive_tax_report({**REPORT, "gifts_donations_lost": gifts}))
    for expected in (
        "05/01/2024 Donation Short 0.01000000 $3,000.00 $900.00 06/01/2024 Donation Both 0.03000000 $3,000.00 "
        "$1,350.00 Total 0.04000000 $6,000.00 $2,250.00",
        "Term Both: the donation of 06/01/2024 was 0.02000000 BTC long-term (cost basis $400.00) and 0.01000000 "
        "BTC short-term (cost basis $950.00).",
        "Donations: the deduction is generally the value of coins held more than a year (Term Long) and the lower "
        "of value and cost basis for the rest (Short), within limits that depend on the charity and your income: "
        "ask your tax preparer.",
        "A deduction over $500 for the year's bitcoin donations together needs Form 8283; over $5,000, also a "
        "qualified appraisal (an exchange's price isn't one) and the charity's signature on it.",
    ):
        assert expected in text, expected
    assert "Gifts: if all you gave" not in text and "Lost coins:" not in text


@pytest.mark.parametrize("year, over", [(2025, "$19,000"), (2026, "$19,000"), (2018, "$15,000"),
                                        (2010, "2010's annual exclusion"), (2031, "2031's annual exclusion")])
def test_the_gift_tax_return_names_the_years_exclusion(year, over):
    """#160: the IRS's annual exclusion for the year where it's known (its
    gift tax FAQ lists 2011 on), else the words."""
    gift = {"date": f"{year}-08-01T12:00:00Z", "asset": "BTC", "amount": 0.02, "fmv_usd": 1200.0, "type": "Gift"}
    text = pdf_text(generate_comprehensive_tax_report({**EMPTY_REPORT, "tax_year": year,
                                                       "gifts_donations_lost": [gift]}))
    assert f"Gifts: if all you gave one person other than your spouse in {year} adds up to more than {over}, " \
           "you generally need" in text


def test_the_digital_asset_question_follows_the_year():
    """#160: Yes for bitcoin disposed of, received as income, a reward or a
    rebate, or given (a transfer of ownership, IRS "Digital assets"); lost
    coins alone aren't named, so they get what doesn't make it Yes."""
    def question(**data) -> str:
        """The summary's line, up to the next table's header."""
        text = pdf_text(generate_comprehensive_tax_report({**EMPTY_REPORT, **data}))
        return text[text.index("Form 1040's digital asset question"):].split(" Income Source")[0]
    sale = {"asset": "BTC", "date_sold": "2023-07-01T03:00:00Z", "amount": 0.1, "kind": "Network fee"}
    rebate = {"date": "2023-03-01T12:00:00Z", "amount": 0.001, "value_usd": 50.0}
    assert question(capital_gains_transactions=[sale]) == \
        "Form 1040's digital asset question: answer Yes, for the bitcoin disposed of (section 2)."
    assert question(rebates=[rebate]) == \
        "Form 1040's digital asset question: answer Yes, for the bitcoin received (section 3)."
    given = {"date": "2023-08-01T12:00:00Z", "asset": "BTC", "amount": 0.02, "fmv_usd": 1200.0, "type": "Donation"}
    assert question(gifts_donations_lost=[given]) == \
        "Form 1040's digital asset question: answer Yes, for the bitcoin given (section 4)."
    no = ("Form 1040's digital asset question: holding bitcoin, buying it with dollars and moving it between your "
          "own wallets don't make the answer Yes; for anything else, see its instructions.")
    assert question() == no
    assert question(gifts_donations_lost=[{**given, "type": "Lost"}]) == no


def test_a_gift_without_its_lots_has_no_cost_basis_never_zero():
    """A report dict made before #160 listed the lots: the cost basis is
    blank, its total too, as an unvalued gift is never $0."""
    gift = {"date": "2024-08-01T12:00:00Z", "asset": "BTC", "amount": 0.02, "fmv_usd": 1200.0, "type": "Gift"}
    text = pdf_text(generate_comprehensive_tax_report({**REPORT, "gifts_donations_lost": [gift]}))
    assert "08/01/2024 Gift 0.02000000 $1,200.00 Total 0.02000000 $1,200.00 Gifts:" in text


def test_a_brokers_form_brings_the_time_zone_note():
    """#160: a broker's form may date a sale in another time zone; said in
    the notes of a year with a box of sales a broker reported."""
    note = ("The IRS hasn't said which time zone sets your dates, so BitcoinTX uses one, your tax timezone, for all "
            "of them. A broker's Form 1099-DA or 1099-B may date a sale in another (UTC, say): a sale near midnight "
            "can show another date there, even another tax year. Check such a sale with your tax preparer.")
    boxes = [{"box": "H", "line": "2", "rows": 1, "proceeds": 10.0, "cost": 5.0, "gain_loss": 5.0}]
    text = pdf_text(generate_comprehensive_tax_report({**REPORT, "form_8949_boxes": boxes}))
    assert note in text[text.rindex("7. Notes"):]


def test_complete_report_with_nothing_in_it():
    text = pdf_text(generate_comprehensive_tax_report(EMPTY_REPORT))
    assert "in the tax timezone (UTC)" in text
    for empty in ("No disposals for Form 8949 in 2023.", "No disposals in 2023.", "No income in 2023.",
                  "No gifts, donations or lost coins in 2023.", "No bitcoin held on December 31, 2023."):
        assert empty in text
    assert "Expenses" not in text  # #58: no transaction could ever fill it
    assert "-0.00" not in text


def test_complete_report_pages_contents_and_numbers():
    """The cover has no running header; every page says "Page N of M"; the
    contents give each section's page."""
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(generate_comprehensive_tax_report(REPORT))).pages]
    assert all(f"Page {n} of {len(pages)}" in text for n, text in enumerate(pages, start=1))
    assert "2024 Bitcoin Tax Report" not in pages[0]
    assert all("2024 Bitcoin Tax Report" in text for text in pages[1:])
    # Where each section starts: the page with its heading, a line "N. Title"
    starts = {n: next(i for i, text in enumerate(pages[1:], start=2)
                      if any(line.startswith(f"{n}. ") for line in text.split("\n")))
              for n in range(1, 8)}  # the seven sections
    # The contents: each entry's page number comes out of the text just before its title
    listed = {int(n): int(page) for page, n in re.findall(r"(\d+) (\d)\. [A-Z]", " ".join(pages[0].split()))}
    assert listed == starts


def test_a_long_report_keeps_every_row_its_headers_and_page_numbers():
    """Review of #63: a table over many pages repeats its header on each,
    loses no row, and the contents still give each section's page."""
    disposals = [{"asset": "BTC", "date_sold": f"2024-{1 + i % 12:02d}-{1 + i % 28:02d}T12:00:00Z",
                  "date_acquired": "2023-01-02T12:00:00Z", "amount": 0.001 + i / 1e6, "cost": 10.0, "proceeds": 20.0,
                  "gain_loss": 10.0, "holding_period": "LONG", "kind": "Sale", "box": "F"} for i in range(150)]
    pdf = generate_comprehensive_tax_report({**REPORT, "capital_gains_transactions": disposals})
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages]
    detail = [text for text in pages if "Gain (loss)" in text and "Kind" in text]
    assert len(detail) >= 4  # the header on every page of the table
    assert sum(" ".join(text.split()).count(" Sale F Long ") for text in detail) == 150
    starts = {n: next(i for i, text in enumerate(pages[1:], start=2)
                      if any(line.startswith(f"{n}. ") for line in text.split("\n")))
              for n in range(1, 8)}  # the seven sections
    listed = {int(n): int(page) for page, n in re.findall(r"(\d+) (\d)\. [A-Z]", " ".join(pages[0].split()))}
    assert listed == starts and starts[3] > starts[2] + 2


def test_transaction_history_of_a_year_without_transactions(auth_client):
    r = auth_client.get("/api/reports/simple_transaction_history", params={"year": 2010, "format": "pdf"})
    assert r.status_code == 200
    assert "TAX YEAR 2010 Transaction History" in pdf_text(r.content)
    assert "No transactions in 2010. " in pdf_text(r.content) + " "


def row(box: str) -> Form8949Row:
    return Form8949Row("0.1 BTC", "01/01/2024", "06/01/2024", Decimal("10"), Decimal("5"), Decimal("5"),
                       "SHORT", box)


@pytest.mark.parametrize("rows, page, message", [
    ([row("A")], 3, "page must be 1 (Part I) or 2 (Part II)"),
    ([row("A")] * 15, 1, "Cannot fit more than 14 rows on one 2024 Form 8949 page"),
    ([row("A"), row("B")], 1, "Rows for one Form 8949 page must share a box, got ['A', 'B']"),
])
def test_form_8949_page_guards(rows, page, message):
    with pytest.raises(ValueError) as refused:
        map_8949_rows_to_field_data(rows, page=page, year=2024)
    assert str(refused.value) == message
