"""
The complete tax report: a tax year's capital gains, income, gifts and
holdings, and the transactions behind them, as a PDF built with ReportLab
from reporting_core.generate_report_data().

A cover (the year's key figures, how the report was made, contents with
page numbers), a one-page summary that ties to Form 8949 and Schedule D,
then the detail: every disposal, income, gifts/donations/lost coins, the
holdings at year end, a page for whoever files the return (what BitcoinTX
fills on the IRS forms and leaves blank), and notes. The look is
pdf_layout.py's.
"""

import datetime
import logging
from collections import Counter
from io import BytesIO
from typing import Any
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Frame, HRFlowable, NextPageTemplate, PageBreak, PageTemplate, Paragraph,
    Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from backend.constants import normalized
from backend.services.reports.pdf_layout import (
    ACCENT, ACCENT_SOFT, DISCLAIMER, FONT, FOOTER_NOTE, INK, RULE, ReportStyles, data_table, draw_footer_note,
    draw_running_header, numbered_canvas,
)
from backend.services.reports.form_8949 import INHERITED
from backend.services.reports.safe_text import pdf_text

logger = logging.getLogger(__name__)

WIDTH = 7.0  # inches between the margins
INCOME_TYPES = ("Income", "Reward", "Interest")
SHORT_TERM_LINES = ("1b", "2", "3")  # Schedule D Part I lines BitcoinTX fills
LONG_TERM_LINES = ("8b", "9", "10")  # Part II

# What each Form 8949 box holds (the checkbox wording, shortened)
BOX_MEANING = {
    "A": "Short-term, on Form 1099-B, basis reported",
    "B": "Short-term, on Form 1099-B, basis not reported",
    "C": "Short-term, not on a Form 1099-B",
    "D": "Long-term, on Form 1099-B, basis reported",
    "E": "Long-term, on Form 1099-B, basis not reported",
    "F": "Long-term, not on a Form 1099-B",
    "G": "Short-term, on Form 1099-DA, basis reported",
    "H": "Short-term, on Form 1099-DA, basis not reported",
    "I": "Short-term, not on a Form 1099-DA or 1099-B",
    "J": "Long-term, on Form 1099-DA, basis reported",
    "K": "Long-term, on Form 1099-DA, basis not reported",
    "L": "Long-term, not on a Form 1099-DA or 1099-B",
}
# The boxes of sales a broker reported (Form 1099-B or 1099-DA)
BROKER_BOXES = ("A", "B", "D", "E", "G", "H", "J", "K")
# A gift-like withdrawal's purpose as a noun: "the loss of 08/02/2025"
KIND_NOUN = {"gift": "gift", "donation": "donation", "lost": "loss"}

# The gift tax annual exclusion per person (IRS, "Frequently asked questions
# on gift taxes"; Instructions for Form 709 (2025): file when the year's
# gifts to someone other than your spouse total more than it), #160
ANNUAL_GIFT_EXCLUSION = {
    **dict.fromkeys(range(2011, 2013), 13_000), **dict.fromkeys(range(2013, 2018), 14_000),
    **dict.fromkeys(range(2018, 2022), 15_000), 2022: 16_000, 2023: 17_000, 2024: 18_000, 2025: 19_000,
    2026: 19_000,
}


def generate_comprehensive_tax_report(report_dict: dict[str, Any]) -> bytes:
    """The PDF of `report_dict`, reporting_core.generate_report_data()'s
    result for one tax year."""
    report = _TaxReport(report_dict)
    buffer = BytesIO()
    doc = _ReportDocument(buffer, report.running_title)
    # Two passes: the contents learn each section's page
    doc.multiBuild(report.story(), canvasmaker=numbered_canvas())
    logger.info(f"Generated comprehensive tax report for {report.year}")
    return buffer.getvalue()


# Gift values are marked when filled in from the price only from 1.2.9 (#255):
# one the AI connector filled before then counts as entered
OLDER_GIFT_VALUES_NOTE = ("A gift's or donation's value (section 4) the AI connector filled in before BitcoinTX "
                          "1.2.9 isn't marked as from the price, so it isn't listed here.")

class _ReportDocument(BaseDocTemplate):
    """Letter pages: the cover without the running header, the rest with it;
    every section heading goes into the contents."""

    def __init__(self, buffer: BytesIO, running_title: str):
        super().__init__(buffer, pagesize=letter, leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                         topMargin=0.9 * inch, bottomMargin=0.95 * inch, title=running_title,
                         author="BitcoinTX")
        frame = Frame(self.leftMargin, self.bottomMargin, self.width, self.height, id="body")
        self.addPageTemplates([
            PageTemplate(id="cover", frames=[frame], onPage=lambda c, d: draw_footer_note(c, FOOTER_NOTE)),
            PageTemplate(id="body", frames=[frame], onPage=lambda c, d: _body_chrome(c, running_title)),
        ])

    def afterFlowable(self, flowable):
        title = getattr(flowable, "toc_title", None)
        if title:
            self.notify("TOCEntry", (0, title, self.page))


def _body_chrome(canvas, running_title: str) -> None:
    draw_running_header(canvas, running_title)
    draw_footer_note(canvas, FOOTER_NOTE)


def fmt_usd(value: float) -> str:
    return f"${value:,.2f}"


def fmt_gain(value: float) -> str:
    """A gain, or a loss in parentheses as on the IRS forms."""
    value = round(value, 2) + 0.0  # no "-0.00"
    return f"(${-value:,.2f})" if value < 0 else fmt_usd(value)


def fmt_btc(value: float) -> str:
    return f"{value:,.8f}"


def fmt_value(value) -> str:
    """A holding's market value; None when that day has no BTC price."""
    return "not priced" if value is None else fmt_usd(value)


def _and_list(items: list[str]) -> str:
    """"2", "2 and 10", "1b, 2 and 10"."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _term(gift: dict) -> str:
    """"Long", "Short" or "Both": the terms of what a gift, donation or loss
    took from its lots (#160); blank in a report made before they were listed."""
    terms = [part["term"] for part in gift.get("lots_by_term", [])]
    return "Both" if len(terms) > 1 else terms[0].capitalize() if terms else ""


def _basis(gift: dict) -> float | None:
    """The cost basis of what a gift, donation or loss took from its lots
    (#160); None in a report made before it was listed, never $0."""
    parts = gift.get("lots_by_term", [])
    return sum(part["cost_basis"] for part in parts) if parts else None


def _or_blank(usd: float | None) -> str:
    return "" if usd is None else fmt_usd(usd)


def _broker_first(boxes: list[dict]) -> str:
    """Exception 2's column (a) for the boxes of sales a broker reported:
    its name before "see attached statement" (Instructions for Form 8949,
    Exception 2's example; #114)."""
    broker = [b["box"] for b in boxes if b["box"] in BROKER_BOXES]
    if not broker:
        return ""
    return f", after the exchange's name in box{'es' if len(broker) > 1 else ''} {_and_list(broker)}"


def _cell_table(rows: list, widths: list, commands: list) -> Table:
    table = Table(rows, colWidths=[w * inch for w in widths])
    table.setStyle(TableStyle(commands))
    return table


class _TaxReport:
    """The report's parts, each a list of flowables."""

    def __init__(self, data: dict[str, Any]):
        self.data = data
        self.year = data.get("tax_year", "Unknown Year")
        self.tz_name = data.get("tax_timezone") or "UTC"
        self.tz = ZoneInfo(self.tz_name)
        self.styles = ReportStyles()
        self.running_title = f"{self.year} Bitcoin Tax Report"
        self.disposals = [d for d in data.get("capital_gains_transactions", []) if d.get("asset") == "BTC"]
        self.income = [t for t in data.get("income_transactions", []) if t.get("asset") == "BTC"]
        self.rebates = data.get("rebates", [])
        self.gifts = [g for g in data.get("gifts_donations_lost", []) if g.get("asset") == "BTC"]
        balances = data.get("end_of_year_balances", [])
        self.lots = [b for b in balances if b.get("asset", "").startswith("BTC")]
        self.year_end_total = next((b for b in balances if b.get("asset") == "Total"), None)

    def story(self) -> list:
        return [
            *self.cover(),
            NextPageTemplate("body"),
            PageBreak(),
            *self.summary(),
            *self.capital_gains_detail(),
            *self.income_detail(),
            *self.gifts_detail(),
            *self.holdings_detail(),
            *self.using_these_forms(),
            *self.notes(),
        ]

    # Building blocks
    def text(self, value, style=None) -> Paragraph:
        # Report data is text, never markup (safe_text.py)
        return Paragraph(pdf_text(value), style or self.styles.cell)

    def number(self, value: str, bold: bool = False) -> Paragraph:
        return self.text(value, self.styles.number_bold if bold else self.styles.number)

    def numbers(self, *values: str, bold: bool = False) -> list:
        return [self.number(v, bold) for v in values]

    def header(self, *labels: str, numbers_from: int) -> list:
        """A table's header cells; columns from `numbers_from` hold figures."""
        return [self.text(label, self.styles.head_number if i >= numbers_from else self.styles.head)
                for i, label in enumerate(labels)]

    def total_label(self) -> Paragraph:
        return self.text("Total", self.styles.cell_bold)

    def section(self, number: int, title: str, intro: str) -> list:
        heading = self.text(f"{number}. {title}", self.styles.heading)
        heading.toc_title = f"{number}. {title}"
        return [
            CondPageBreak(2.2 * inch),
            # spaceBefore, unlike a Spacer, is dropped at the top of a page
            HRFlowable(width=0.45 * inch, thickness=2.5, color=ACCENT, hAlign="LEFT", spaceBefore=24, spaceAfter=7),
            heading,
            self.text(intro, self.styles.intro),
        ]

    def subheading(self, title: str) -> list:
        """A table's title, on a page with room for it and a few of its rows."""
        return [CondPageBreak(1.3 * inch), self.text(title, self.styles.subheading)]

    def nothing(self, what: str) -> Paragraph:
        return self.text(f"No {what} in {self.year}.", self.styles.normal)

    def date(self, iso: str) -> str:
        """An ISO 8601 timestamp as MM/DD/YYYY in the tax timezone, like the
        IRS forms."""
        if not iso:
            return ""
        try:
            moment = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=datetime.timezone.utc)
            return moment.astimezone(self.tz).strftime("%m/%d/%Y")
        except ValueError:
            return iso

    # Figures used in more than one place
    def gains_by_term(self) -> dict[str, dict[str, float]]:
        summary = self.data.get("capital_gains_summary") or {}
        empty = {"proceeds": 0.0, "basis": 0.0, "gain": 0.0, "profits": 0.0, "losses": 0.0}
        terms = {term: {**empty, **summary.get(term, {})} for term in ("short_term", "long_term")}
        terms["total"] = {k: terms["short_term"][k] + terms["long_term"][k] for k in empty}
        return terms

    def income_total(self) -> float:
        return sum(t.get("value_usd", 0.0) for t in self.income if t.get("type") in INCOME_TYPES)

    def start_of_year(self) -> tuple[float, float, float | None]:
        """BTC held on January 1: quantity, cost basis, market value (None: not priced)."""
        quantity = cost = 0.0
        value = 0.0
        for row in self.data.get("start_of_year_balances", []):
            quantity += row.get("quantity", 0.0)
            cost += row.get("quantity", 0.0) * row.get("avg_cost_basis", 0.0)
            value = None if row.get("value") is None or value is None else value + row["value"]
        return quantity, cost, value

    # The cover
    def cover(self) -> list:
        s = self.styles
        return [
            Spacer(1, 0.3 * inch),
            self.text(f"TAX YEAR {self.year}", s.kicker),
            Spacer(1, 6),
            self.text("Bitcoin Tax Report", s.title),
            Spacer(1, 4),
            self.text(f"Capital gains, income and holdings, January 1 to December 31, {self.year}", s.subtitle),
            Spacer(1, 0.35 * inch),
            self.key_figures(),
            Spacer(1, 0.3 * inch),
            *self.subheading("About this report"),
            self.facts(),
            Spacer(1, 0.25 * inch),
            *self.subheading("Contents"),
            self.contents(),
        ]

    def key_figures(self) -> Table:
        terms = self.gains_by_term()
        total = self.year_end_total or {}
        cards = [
            ("NET CAPITAL GAIN (LOSS)", fmt_gain(terms["total"]["gain"]),
             f"Short-term {fmt_gain(terms['short_term']['gain'])} · Long-term {fmt_gain(terms['long_term']['gain'])}"),
            ("INCOME", fmt_usd(self.income_total()), "Income, rewards and interest received"),
            ("BITCOIN HELD AT YEAR END", f"{fmt_btc(total.get('quantity', 0.0))} BTC",
             f"Cost basis {fmt_usd(total.get('cost', 0.0))}"),
            ("VALUE AT YEAR END", fmt_value(total.get("value", 0.0)), f"December 31, {self.year}"),
        ]
        s = self.styles
        cells = [[self.text(label, s.label), self.text(value, s.metric), self.text(detail, s.metric_detail)]
                 for label, value, detail in cards]
        return _cell_table([cells[:2], cells[2:]], [WIDTH / 2] * 2, [
            ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT),
            ("LINEBELOW", (0, 0), (-1, 0), 6, colors.white),
            ("LINEAFTER", (0, 0), (0, -1), 6, colors.white),
            ("LINEBEFORE", (0, 0), (-1, -1), 2.5, ACCENT),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 11),
            ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ])

    def facts(self) -> Table:
        facts = (
            ("Tax year", f"{self.year} ({self.data.get('period', '')})"),
            ("Cost basis method", "First in, first out (FIFO), for each account"),
            ("Tax timezone", f"{self.tz_name}: it decides each transaction's tax year, the dates shown "
                             "and the holding period"),
            ("Prices", "USD values as entered; one left blank: the BTC price when its hour began (UTC), "
                       "else that day's"),
            ("Generated", f"{self.data.get('report_date', '')} UTC"),
        )
        made = self.made_before_year_end()
        if made:
            # One line, so the contents stay on the cover with a long timezone
            facts += (("Year not over", f"Made {made}: figures to that day only"),)
        rows = [[self.text(label.upper(), self.styles.label), self.text(value, self.styles.normal)]
                for label, value in facts]
        return _cell_table(rows, [1.5, WIDTH - 1.5], [
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ])

    def contents(self) -> TableOfContents:
        toc = TableOfContents(dotsMinLevel=0, rightColumnWidth=0.5 * inch)
        toc.levelStyles = [ParagraphStyle(name="Contents", fontName=FONT, fontSize=9.5, leading=15,
                                          textColor=INK)]
        return toc

    # 1. Summary
    def summary(self) -> list:
        return [
            *self.section(1, "Summary", f"The year {self.year} at a glance: the totals of the detail in the "
                                        "sections that follow, and the holdings the year started and ended with."),
            *self.subheading("Capital gains and losses"),
            self.gains_table(),
            *self.subheading("Form 8949 and Schedule D"),
            *self.boxes_table(),
            *self.subheading("Income"),
            self.income_summary_table(),
            *self.subheading("Bitcoin holdings"),
            *self.holdings_summary(),
            PageBreak(),
        ]

    def digital_asset_question(self) -> str:
        """
        How to answer the digital asset question at the top of Form 1040
        (#160), in one line: the summary page has a line to spare with all
        six boxes, section 6 none. Instructions for Form 1040 (2025),
        "Digital Assets": Yes for digital assets received as payment, as a
        reward or award, or from mining or staking, and for any sale,
        exchange or other disposal; not for holding, buying with real
        currency or moving them between your own wallets alone. IRS "Digital
        assets" page: a transfer fee paid in digital assets, or a transfer
        of ownership (a gift or donation given), makes it Yes. A rebate (a
        card's sats-back) is received as a reward. Lost coins aren't named.
        """
        given = [g for g in self.gifts if normalized(g.get("type")) in ("gift", "donation")]
        did = [part for part, shown in (("disposed of (section 2)", self.disposals),
                                        ("received (section 3)", self.income or self.rebates),
                                        ("given (section 4)", given)) if shown]
        if did:
            return f"Form 1040's digital asset question: answer Yes, for the bitcoin {_and_list(did)}."
        return ("Form 1040's digital asset question: holding bitcoin, buying it with dollars and moving it between "
                "your own wallets don't make the answer Yes; for anything else, see its instructions.")

    def gains_table(self) -> Table:
        terms = self.gains_by_term()
        counts = Counter((d.get("holding_period") or "").upper() for d in self.disposals)
        rows = [self.header("Term", "Disposals", "Proceeds", "Cost basis", "Gains", "Losses",
                            "Net gain (loss)", numbers_from=1)]
        for label, key, count in (("Short-term", "short_term", counts["SHORT"]),
                                  ("Long-term", "long_term", counts["LONG"])):
            t = terms[key]
            rows.append([self.text(label), *self.numbers(
                str(count), fmt_usd(t["proceeds"]), fmt_usd(t["basis"]), fmt_usd(t["profits"]),
                fmt_gain(-t["losses"]), fmt_gain(t["gain"]))])
        t = terms["total"]
        rows.append([self.total_label(), *self.numbers(
            str(len(self.disposals)), fmt_usd(t["proceeds"]), fmt_usd(t["basis"]), fmt_usd(t["profits"]),
            fmt_gain(-t["losses"]), fmt_gain(t["gain"]), bold=True)])
        return data_table(rows, [1.1, 0.8, 1.1, 1.1, 0.95, 0.95, 1.0], total=True)

    def boxes_table(self) -> list:
        boxes = self.data.get("form_8949_boxes", [])
        question = self.text(self.digital_asset_question(), self.styles.note)
        if not boxes:
            return [self.nothing("disposals for Form 8949"), question]
        rows = [self.header("Box", "What it holds", "Sch. D line", "Rows", "Proceeds", "Cost basis",
                            "Gain (loss)", numbers_from=2)]
        for b in boxes:
            rows.append([self.text(b["box"], self.styles.cell_bold), self.text(BOX_MEANING.get(b["box"], "")),
                         *self.numbers(b["line"], str(b["rows"]), fmt_usd(b["proceeds"]), fmt_usd(b["cost"]),
                                       fmt_gain(b["gain_loss"]))])
        return [
            data_table(rows, [0.4, 2.35, 0.65, 0.45, 1.05, 1.05, 1.05]),
            self.text("Each box takes a page or more of Form 8949, and its totals go on the Schedule D line "
                      "shown. For the years BitcoinTX has the IRS forms of, they are the totals of the forms it "
                      "fills (Reports: IRS Reports).", self.styles.note),
            question,
        ]

    def income_summary_table(self) -> Table:
        rows = [self.header("Source", "Deposits", "BTC", "Value (USD)", numbers_from=1)]
        for source in INCOME_TYPES:
            items = [t for t in self.income if t.get("type") == source]
            rows.append([self.text(source), *self.numbers(
                str(len(items)), fmt_btc(sum(t.get("amount", 0.0) for t in items)),
                fmt_usd(sum(t.get("value_usd", 0.0) for t in items)))])
        rows.append([self.total_label(), *self.numbers(
            str(len(self.income)), fmt_btc(sum(t.get("amount", 0.0) for t in self.income)),
            fmt_usd(self.income_total()), bold=True)])
        return data_table(rows, [2.2, 1.2, 1.8, 1.8], total=True)

    def holdings_summary(self) -> list:
        quantity, cost, value = self.start_of_year()
        end = self.year_end_total or {"quantity": 0.0, "cost": 0.0, "value": 0.0}
        rows = [self.header("Held on", "BTC", "Cost basis", "Avg cost per BTC", "Market value", numbers_from=1)]
        for label, qty, basis, worth in ((f"January 1, {self.year}", quantity, cost, value),
                                         (f"December 31, {self.year}", end.get("quantity", 0.0),
                                          end.get("cost", 0.0), end.get("value"))):
            rows.append([self.text(label), *self.numbers(
                fmt_btc(qty), fmt_usd(basis), fmt_usd(basis / qty if qty > 0 else 0.0),
                fmt_value(worth) if qty > 0 else fmt_usd(0.0))])
        story = [data_table(rows, [1.6, 1.35, 1.35, 1.35, 1.35])]
        if quantity > 0 and value is None:
            story.append(self.text(
                f"No BTC price is stored for {self.year}-01-01, so the holdings aren't valued "
                "(price lookups: Settings > Privacy & Network).", self.styles.note))
        if self.lots:
            story.append(self.price_note())
        return story

    def price_note(self) -> Paragraph:
        """How the year-end holdings are valued: the price, or why there is none."""
        note = self.lots[0].get("description", "")
        if note.startswith("@ "):
            note = f"Market value at {note[2:]}."
        return self.text(note, self.styles.note)

    # 2. Capital gains and losses
    def capital_gains_detail(self) -> list:
        story = self.section(2, "Capital gains and losses",
                             "Every disposal of the year as on Form 8949: one line for each lot it used (first in, "
                             "first out), with its box. A network fee paid in BTC is a disposal too.")
        if not self.disposals:
            return story + [self.nothing("disposals")]
        rows = [self.header("Sold", "Acquired", "Kind", "Box", "Term", "BTC", "Proceeds", "Cost basis",
                            "Gain (loss)", numbers_from=5)]
        rows += [self.disposal_row(d) for d in self.disposals]
        t = self.gains_by_term()["total"]
        rows.append([self.total_label(), "", "", "", "", *self.numbers(
            fmt_btc(sum(d.get("amount", 0.0) for d in self.disposals)), fmt_usd(t["proceeds"]),
            fmt_usd(t["basis"]), fmt_gain(t["gain"]), bold=True)])
        # Acquired fits INHERITED (43 pt at 8 pt, #154) on one line, Kind "Network fee"
        return story + [data_table(rows, [0.72, 0.75, 0.79, 0.38, 0.5, 0.86, 1.0, 1.0, 1.0], total=True)]

    def disposal_row(self, d: dict) -> list:
        return [
            self.text(self.date(d.get("date_sold", ""))), self.text(self.date(d.get("date_acquired", ""))),
            self.text(d.get("kind") or d.get("type", "")), self.text(d.get("box", "")),
            self.text((d.get("holding_period") or "").capitalize()),
            *self.numbers(fmt_btc(d.get("amount", 0.0)), fmt_usd(d.get("proceeds", 0.0)),
                          fmt_usd(d.get("cost", 0.0)), fmt_gain(d.get("gain_loss", 0.0))),
        ]

    # 3. Income
    def income_detail(self) -> list:
        story = self.section(3, "Income", "Bitcoin received as income, rewards or interest, valued when it was "
                                          "received. That value is the income to report and the coins' cost basis.")
        if not self.income:
            return story + [self.nothing("income")] + self.rebates_detail()
        rows = [self.header("Received", "Source", "BTC", "Value (USD)", numbers_from=2)]
        rows += [[self.text(self.date(t.get("date", ""))), self.text(t.get("type", "")),
                  *self.numbers(fmt_btc(t.get("amount", 0.0)), fmt_usd(t.get("value_usd", 0.0)))]
                 for t in self.income]
        rows.append([self.total_label(), "", *self.numbers(
            fmt_btc(sum(t.get("amount", 0.0) for t in self.income)), fmt_usd(self.income_total()), bold=True)])
        story.append(data_table(rows, [1.4, 2.0, 1.8, 1.8], total=True))
        if any(t.get("type") == "Income" for t in self.income):
            # IRS digital asset FAQ Q60 (Part II, added Dec. 15, 2025; Part I's
            # Q10): an independent contractor's pay in digital assets is
            # self-employment income at its value when received; the IRS
            # "Digital assets" page: reported on Schedule C (#160)
            story.append(self.text("Income paid for your work as an independent contractor goes on Schedule C, "
                                   "at the same value, and is self-employment income (Schedule SE).",
                                   self.styles.note))
        return story + self.rebates_detail()

    def rebates_detail(self) -> list:
        """Rebates (#98), listed so they can be checked: not income, but
        their value at receipt is the coins' cost basis."""
        if not self.rebates:
            return []
        rows = [self.header("Received", "BTC", "Value (USD)", numbers_from=1)]
        rows += [[self.text(self.date(r.get("date", ""))),
                  *self.numbers(fmt_btc(r.get("amount", 0.0)), fmt_usd(r.get("value_usd", 0.0)))]
                 for r in self.rebates]
        rows.append([self.total_label(), *self.numbers(fmt_btc(sum(r.get("amount", 0.0) for r in self.rebates)),
                                                       fmt_usd(sum(r.get("value_usd", 0.0) for r in self.rebates)),
                                                       bold=True)])
        return [*self.subheading("Rebates (not income)"),
                self.text("Bitcoin back for spending, such as a rewards card's sats-back, entered as a Rebate: "
                          "generally treated like a rebate on the purchase price, not income (by analogy with "
                          "Rev. Rul. 76-96; the IRS has no ruling on bitcoin back for spending). Its value when received "
                          "is the coins' cost basis.", self.styles.note),
                Spacer(1, 6),
                data_table(rows, [2.4, 2.3, 2.3], total=True)]

    # 4. Gifts, donations and lost coins
    def gifts_detail(self) -> list:
        story = self.section(4, "Gifts, donations and lost coins",
                             "Bitcoin given away, donated or lost. These are not sales, so they have no gain or loss "
                             "of their own; a network fee paid with them is a disposal (section 2).")
        if not self.gifts:
            return story + [self.nothing("gifts, donations or lost coins")]
        # The cost basis and term of what each took from its lots (#160): a
        # donation's deduction, a gift's Form 709 and a theft's Form 4684 need them
        rows = [self.header("Date", "Kind", "Term", "BTC", "Fair market value", "Cost basis", numbers_from=3)]
        for g in self.gifts:
            fmv = g.get("fmv_usd")
            rows.append([self.text(self.date(g.get("date", ""))), self.text(g.get("type", "")),
                         self.text(_term(g)), *self.numbers(
                             fmt_btc(g.get("amount", 0.0)), fmt_usd(fmv) if fmv is not None else "not given",
                             _or_blank(_basis(g)))])
        bases = [basis for basis in map(_basis, self.gifts) if basis is not None]
        rows.append([self.total_label(), "", "", *self.numbers(
            fmt_btc(sum(g.get("amount", 0.0) for g in self.gifts)), self.fmv_total(),
            _or_blank(sum(bases) if bases else None), bold=True)])
        return story + [data_table(rows, [0.85, 0.85, 0.6, 1.3, 1.75, 1.65], total=True), *self.gift_notes()]

    def gift_notes(self) -> list:
        """What each kind in the list means for the return, only for the
        kinds the year has (#160); the IRS sources in comments."""
        kinds = {normalized(g.get("type")) for g in self.gifts}
        notes = [self.both_terms_note()] if any(_term(g) == "Both" for g in self.gifts) else []
        if "donation" in kinds:
            # IRS digital asset FAQ Q78 (Part II; Part I's Q35): generally the
            # value if held more than a year, else the lower of basis and value
            # (IRC §170(e)(1)(A)); Q78 and CCA 202302012: over $5,000 a qualified
            # appraisal, an exchange's price isn't one; Instructions for Form 8283:
            # over $500, similar items of the year combined; Q79: the charity signs
            notes.append("Donations: the deduction is generally the value of coins held more than a year (Term "
                         "Long) and the lower of value and cost basis for the rest (Short), within limits that "
                         "depend on the charity and your income: ask your tax preparer. A deduction over $500 for "
                         "the year's bitcoin donations together needs Form 8283; over $5,000, also a qualified "
                         "appraisal (an exchange's price isn't one) and the charity's signature on it.")
        if "gift" in kinds:
            # Instructions for Form 709 (2025): the year's gifts to someone
            # "(other than to your spouse)" over the annual exclusion (a spouse
            # who isn't a U.S. citizen has a higher one)
            limit = ANNUAL_GIFT_EXCLUSION.get(self.year)
            over = fmt_usd(limit).removesuffix(".00") if limit else f"{self.year}'s annual exclusion"
            notes.append(f"Gifts: if all you gave one person other than your spouse in {self.year} adds up to more "
                         f"than {over}, you generally need to file a gift tax return, Form 709.")
        if "lost" in kinds:
            # CCA 202511015: a theft in a transaction entered into for profit
            # (IRC §165(c)(2)) is deductible on Form 4684, Section B, up to its
            # basis (§165(b)), in the year it's discovered
            notes.append("Lost coins: BitcoinTX records no loss for them. A theft or scam loss in an investment "
                         "made for profit may be deductible on Form 4684, Section B (not Form 8949), up to the "
                         "coins' cost basis: ask your tax preparer.")
        return [self.text(note, self.styles.note) for note in notes]

    def both_terms_note(self) -> str:
        """Each gift of coins of both terms, split: the deduction of a
        donation's two parts follows different rules."""
        split = [f"the {KIND_NOUN.get(normalized(g.get('type')), 'gift')} of {self.date(g.get('date', ''))} was "
                 + " and ".join(f"{fmt_btc(p['btc'])} BTC {p['term'].lower()}-term (cost basis "
                                f"{fmt_usd(p['cost_basis'])})" for p in g["lots_by_term"])
                 for g in self.gifts if _term(g) == "Both"]
        return f"Term Both: {'; '.join(split)}."

    def fmv_total(self) -> str:
        """The values given, and how many are not: an unvalued gift is never $0."""
        given = [g["fmv_usd"] for g in self.gifts if g.get("fmv_usd") is not None]
        missing = len(self.gifts) - len(given)
        if not given:
            return "not given"
        return fmt_usd(sum(given)) + (f" + {missing} not given" if missing else "")

    # 5. Holdings at year end
    def holdings_detail(self) -> list:
        story = self.section(5, "Holdings at year end",
                             f"The bitcoin held on December 31, {self.year}, by account and lot by lot: what the "
                             "next year starts from, and the cost basis of each future sale.")
        if not self.lots:
            return story + [self.text(f"No bitcoin held on December 31, {self.year}.", self.styles.normal)]
        total = self.year_end_total or {}
        quantity = total.get("quantity", 0.0)
        return story + [
            self.by_account_table(),
            self.price_note(),
            self.text(f"Average cost: {fmt_usd(total.get('cost', 0.0) / quantity if quantity else 0.0)} per BTC",
                      self.styles.note),
            *self.subheading("Lot by lot"),
            self.lots_table(),
        ]

    def by_account_table(self) -> Table:
        accounts: dict[str, dict] = {}
        for lot in self.lots:
            acc = accounts.setdefault(lot.get("account") or "Bitcoin",
                                      {"lots": 0, "btc": 0.0, "cost": 0.0, "value": 0.0})
            acc["lots"] += 1
            acc["btc"] += lot.get("quantity", 0.0)
            acc["cost"] += lot.get("cost", 0.0)
            acc["value"] = None if lot.get("value") is None or acc["value"] is None else acc["value"] + lot["value"]
        rows = [self.header("Account", "Lots", "BTC", "Cost basis", "Market value", numbers_from=1)]
        rows += [[self.text(name), *self.numbers(str(a["lots"]), fmt_btc(a["btc"]), fmt_usd(a["cost"]),
                                                 fmt_value(a["value"]))] for name, a in sorted(accounts.items())]
        total = self.year_end_total or {}
        rows.append([self.total_label(), *self.numbers(
            str(len(self.lots)), fmt_btc(total.get("quantity", 0.0)), fmt_usd(total.get("cost", 0.0)),
            fmt_value(total.get("value")), bold=True)])
        return data_table(rows, [2.2, 0.8, 1.4, 1.3, 1.3], total=True)

    def lots_table(self) -> Table:
        rows = [self.header("Acquired", "Account", "BTC", "Cost basis", "Market value", numbers_from=2)]
        rows += [[self.text(self.date(lot.get("acquired", ""))), self.text(lot.get("account", "")),
                  *self.numbers(fmt_btc(lot.get("quantity", 0.0)), fmt_usd(lot.get("cost", 0.0)),
                                fmt_value(lot.get("value")))] for lot in self.lots]
        total = self.year_end_total or {}
        rows.append([self.total_label(), "", *self.numbers(
            fmt_btc(total.get("quantity", 0.0)), fmt_usd(total.get("cost", 0.0)), fmt_value(total.get("value")),
            bold=True)])
        return data_table(rows, [1.2, 1.8, 1.4, 1.3, 1.3], total=True)

    # 6. Using these forms
    def using_these_forms(self) -> list:
        """For whoever files the return (a preparer, often): what BitcoinTX
        fills on Form 8949 and Schedule D, what it leaves blank on purpose
        and why (the owner's decision, #79: never a carryover, nor the lines
        that depend on the rest of the return), and the Bitcoin-only figures."""
        # On a new page, to hand to whoever files the return
        story = [PageBreak(), *self.section(6, "Using these forms",
                             "For whoever files the return: what BitcoinTX fills on Form 8949 and Schedule D "
                             "(Reports: IRS Reports), what it leaves blank on purpose, and why.")]
        unfinished = self.year_not_over()
        if unfinished:
            story.append(self.text(unfinished, self.styles.normal))
        story += self.subheading("What BitcoinTX fills")
        story += self.bullets(self.filled_notes())
        story += self.subheading("What BitcoinTX leaves blank, and why")
        story += self.bullets((
            "Schedule D lines 1a and 8a: every sale goes on Form 8949, as Schedule D allows, so they stay blank.",
            "Schedule D lines 6 and 14, the loss carryovers: they come from last year's return.",
            "Lines 4, 5, 11, 12 and 13, other sources (installment sales, casualties, K-1s, capital gain "
            "distributions and the like): BitcoinTX tracks only bitcoin.",
            "Lines 7, 15, 16 and 21, and the rest of Part III: they combine the Bitcoin lines with everything "
            "else on the return.",
            "The qualified opportunity fund question at the top of Schedule D: answer it.",
        ))
        story += self.subheading("The Bitcoin-only figures")
        story += self.bitcoin_only_figures()
        story += self.subheading("Before filing")
        story += self.bullets(self.filing_notes())
        return story

    def made_before_year_end(self) -> str | None:
        """The day (MM/DD/YYYY, tax timezone) the report was made, when that
        was before the tax year ended."""
        try:
            made = datetime.datetime.strptime(self.data.get("report_date", ""), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
        made = made.replace(tzinfo=datetime.timezone.utc).astimezone(self.tz)
        if not isinstance(self.year, int) or made.year > self.year:
            return None
        return made.strftime("%m/%d/%Y")

    def year_not_over(self) -> str | None:
        """A note when the report was made before the tax year ended."""
        made = self.made_before_year_end()
        return made and (f"The year isn't over yet: this report was made on {made}, so its figures cover "
                         "January 1 to that day only. Make it again after December 31 to file.")

    def filled_notes(self) -> list[str]:
        """What Reports: IRS Reports prints for the year. `irs_forms` is the
        route's: "final", "draft", "none" (a year before BitcoinTX's forms) or
        "newer" (after them); a report made without it says nothing of it."""
        boxes = self.data.get("form_8949_boxes", [])
        forms = self.data.get("irs_forms", "final")
        # The letters only: section 1's box table says what each holds
        listed = f"{_and_list([b['box'] for b in boxes])} (what each holds: section 1)" if boxes else ""
        lines = _and_list([b["line"] for b in boxes]) if boxes else ""
        each = "each the total of its box's" if len(boxes) > 1 else "the total of its box's"
        if not boxes:
            notes = [f"No disposals in {self.year}: there is no Form 8949, and Schedule D's Bitcoin lines are blank."]
        elif forms in ("none", "newer"):
            # Code M's row of the column (f) table: "Enter -0- in column (g)
            # unless an adjustment is required because of another code" (#114)
            notes = [
                f"Fill Form 8949 from section 2's list, a page or more per box, or attach that list as a statement "
                f"and enter each box's totals on Form 8949 (Exception 2 of its instructions): column (a) \"see "
                f"attached statement\"{_broker_first(boxes)}; (b) and (c) blank; (f) code M; (g) -0-. This year's "
                f"boxes: {listed}.",
                f"Schedule D: line{'s' if len(boxes) > 1 else ''} {lines}, {each} Form 8949 entries, as in the "
                "Summary.",
            ]
        else:
            notes = [
                f"Form 8949: every Bitcoin disposal of {self.year}, a page or more per box, each page's line 2 "
                f"adding up its rows. This year's boxes: {listed}.",
                f"Schedule D: line{'s' if len(boxes) > 1 else ''} {lines}, {each} Form 8949 pages. Column (g) "
                "is blank: BitcoinTX records no adjustments.",
            ]
        if forms == "draft":
            notes.append(f"The {self.year} forms are the IRS's drafts, marked DRAFT — DO NOT FILE: file on the "
                         "final forms, with the same figures.")
        elif forms == "none":
            notes.insert(0, f"BitcoinTX has no IRS forms for {self.year}, so it fills none.")
        elif forms == "newer":
            notes.insert(0, f"BitcoinTX has no IRS forms for {self.year} yet, so it fills none: a newer "
                            "BitcoinTX may have them.")
        return notes

    def bitcoin_only_figures(self) -> list:
        """Lines 7, 15 and 16 as they would be with no other capital asset and
        no carryover, and line 21's rule for a net loss."""
        boxes = self.data.get("form_8949_boxes", [])
        short = round(sum(b["gain_loss"] for b in boxes if b["line"] in SHORT_TERM_LINES), 2)
        long_ = round(sum(b["gain_loss"] for b in boxes if b["line"] in LONG_TERM_LINES), 2)
        net = round(short + long_, 2)
        rows = [self.header("Schedule D line", "If bitcoin is the only capital asset and there's no carryover",
                            numbers_from=1),
                [self.text("7  Net short-term gain (loss)"), self.number(fmt_gain(short))],
                [self.text("15  Net long-term gain (loss)"), self.number(fmt_gain(long_))],
                [self.text("16  Lines 7 and 15 combined", self.styles.cell_bold), self.number(fmt_gain(net), True)]]
        if net < 0:
            rule = (f"Line 16 is a loss: line 21 is the smaller of the loss ({fmt_usd(-net)}) and $3,000, or $1,500 "
                    "if married filing separately; a loss not deducted may carry over to next year (the Capital Loss "
                    "Carryover Worksheet).")
        else:
            rule = "Line 16 isn't a loss, so line 21 doesn't apply."
        return [data_table(rows, [3.2, 3.8], total=True), self.text(rule, self.styles.note)]

    def filing_notes(self) -> list[str]:
        # Only in a year with rebates (#98), so the page stays one page otherwise
        rebates = ["Rebates (bitcoin back for spending, listed in section 3) aren't counted as income; their "
                   "value when received is their cost basis."] if self.rebates else []
        # Only in a year with a disposal of inherited coins (#154)
        inherited = ["Inherited bitcoin (deposits with source Inherited) is long-term whenever it's sold (IRC "
                     "§1223(9)), with INHERITED in Form 8949's column (b). Its cost basis is its value on the date "
                     "of death, or on the estate's alternate valuation date if it chose one (IRC §1014(a)). If the "
                     "estate reported a value to you on Form 8971, Schedule A, as having increased the estate tax, "
                     "the basis can't be more than that value (IRC §1014(f))."] \
            if any(d.get("date_acquired") == INHERITED for d in self.disposals) else []
        return [
            "Write the name and social security number on every Form 8949 page and on Schedule D: BitcoinTX "
            "leaves them blank, and a Part II page can print without its Part I.",
            "Print single-sided: otherwise Schedule D can start on the back of the last Form 8949 page.",
            "BitcoinTX tracks one self-custody wallet and one exchange account, each with its own lots, first in, "
            "first out. Since 2025 IRS rules require cost basis to be figured wallet by wallet and account by "
            "account (Treas. Reg. §1.1012-1(j); Rev. Proc. 2024-28): multiple wallets or exchange accounts are "
            "pooled here and need separate records.",
            "Gifts received use the giver's cost basis and, when entered, the giver's acquisition date. BitcoinTX "
            "doesn't apply the rule for a gift worth less on the day of the gift than the giver paid (IRC §1015): "
            "a sale of such coins at a loss has to be adjusted by hand (its basis and holding period).",
            *rebates,
            *inherited,
            DISCLAIMER,
        ]

    def bullets(self, notes) -> list:
        return [Paragraph(pdf_text(note), self.styles.bullet, bulletText="•") for note in notes]

    # 7. Notes
    def notes(self) -> list:
        notes = (
            "All amounts are in US dollars unless marked BTC. Losses are shown in parentheses, as on the IRS forms.",
            "Capital gains use the first in, first out (FIFO) method within each account: a disposal uses the "
            "oldest bitcoin held in that account. Trading between BTC and USD is a taxable event.",
            "A disposal is long-term when the bitcoin was held more than one year (disposed of after the first "
            "anniversary of its acquisition), or was inherited; otherwise it is short-term.",
            "USD values are the ones entered with each transaction. When one was left blank, BitcoinTX filled "
            "it in from the U.S. dollar price of bitcoin when the transaction's hour began (UTC): Bitstamp's "
            "hourly opening price, downloaded by BitcoinTX and checked against fingerprints published with it, "
            "or your own Mempool server's record of that hour. Where it had no hourly price (before 2013, or "
            "none on this install), and for a value filled in before hourly prices, it used that day's 00:00 "
            "UTC price; an inheritance is valued at its date of death's 00:00 UTC price. The values it filled in "
            "(income, rebates, inherited coins, spends, gifts, donations, lost coins and network fees), and the "
            "price each used, are listed below.",
            "IRS rules measure fair market value at the date and time of each transaction (Treas. Reg. "
            "§1.1001-7(b)(3)); an hourly price approximates it. The IRS has not approved any price source or "
            "method: you are responsible for showing your values are accurate. A value from your own records "
            "is better evidence: the dollar amount an exchange credited for a reward, or the value of what you "
            "bought with bitcoin you spent.",
            "Holdings are valued at the price when the tax year began and ended (midnight in the tax "
            "timezone): the hour's price, or that day's 00:00 UTC price where there's none.",
            f"All dates are shown as MM/DD/YYYY (the IRS format) in the tax timezone ({self.tz_name}).",
            *self.broker_dates(),
            "A Form 8949 box follows what a broker reports on Form 1099-B or 1099-DA; a transaction's "
            "Broker form setting records what your broker's form actually showed.",
            "This report is prepared from your own records: check it with a tax professional before you file.",
        )
        return [*self.section(7, "Notes", "How the figures in this report are made."), *self.bullets(notes),
                *self.priced_values()]

    def broker_dates(self) -> list[str]:
        """Why a broker's form can date a sale differently, in a year with a
        box of sales a broker reported (#160). No IRS rule says which time
        zone sets an individual's dates (the digital asset FAQ speaks only of
        "the date and time" of a transaction), and the Instructions for Form
        1099-DA name none for the broker: the tax timezone is BitcoinTX's
        choice, one zone for every date."""
        if not any(b["box"] in BROKER_BOXES for b in self.data.get("form_8949_boxes", [])):
            return []
        return ["The IRS hasn't said which time zone sets your dates, so BitcoinTX uses one, your tax timezone, "
                "for all of them. A broker's Form 1099-DA or 1099-B may date a sale in another (UTC, say): a sale "
                "near midnight can show another date there, even another tax year. Check such a sale with your "
                "tax preparer."]

    def priced_values(self) -> list:
        """The year's values filled in from the BTC price, and which price (#144)."""
        rows = self.data.get("priced_values", [])
        story = self.subheading("Values from the BTC price")
        if not rows:
            return story + [self.text(f"None of {self.year}'s values: each was entered with its transaction.",
                                      self.styles.normal),
                            *([self.text(OLDER_GIFT_VALUES_NOTE, self.styles.note)] if self.gifts else [])]
        table = [self.header("Date", "Transaction", "Value", "Price used", "USD", numbers_from=4)]
        table += [[self.text(self.date(r["date"])), self.text(r["transaction"]), self.text(r["value"]),
                   self.text(r["priced_at"]), self.number(fmt_usd(r["usd"]))] for r in rows]
        return story + [self.text(self.priced_values_note(), self.styles.note),
                        Spacer(1, 6), data_table(table, [0.85, 1.35, 1.35, 2.55, 0.9])]

    def priced_values_note(self) -> str:
        return ("Every other value of the year was entered with its transaction. A lot's cost basis from an "
                "earlier year is listed in that year's report."
                + (f" {OLDER_GIFT_VALUES_NOTE}" if self.gifts else ""))
