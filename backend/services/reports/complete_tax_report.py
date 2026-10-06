"""
The complete tax report: a tax year's capital gains, income, gifts and
holdings, and the transactions behind them, as a PDF built with ReportLab
from reporting_core.generate_report_data().

A cover (the year's key figures, how the report was made, contents with
page numbers), a one-page summary that ties to Form 8949 and Schedule D,
then the detail: every disposal, income, gifts/donations/lost coins, the
holdings at year end, and notes. The look is pdf_layout.py's.
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

from backend.services.reports.pdf_layout import (
    ACCENT, ACCENT_SOFT, FONT, INK, RULE, ReportStyles, data_table, draw_footer_note, draw_running_header,
    numbered_canvas,
)
from backend.services.reports.safe_text import pdf_text

logger = logging.getLogger(__name__)

WIDTH = 7.0  # inches between the margins
INCOME_TYPES = ("Income", "Reward", "Interest")
FOOTER_NOTE = "Prepared with BitcoinTX from your own records. Check it with your tax advisor before filing."

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
        self.income = [t for t in data.get("income_transactions", []) if t.get("asset") in ("BTC", "USD")]
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
            ("Prices", "USD values as entered with each transaction; a value left blank comes from that "
                       "day's stored daily BTC price"),
            ("Generated", f"{self.data.get('report_date', '')} UTC"),
        )
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
            *self.section(1, "Summary", f"The year {self.year} at a glance. Each figure is the total of the "
                                        "detail in the sections that follow."),
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
        if not boxes:
            return [self.nothing("disposals for Form 8949")]
        rows = [self.header("Box", "What it holds", "Sch. D line", "Rows", "Proceeds", "Cost basis",
                            "Gain (loss)", numbers_from=2)]
        for b in boxes:
            rows.append([self.text(b["box"], self.styles.cell_bold), self.text(BOX_MEANING.get(b["box"], "")),
                         *self.numbers(b["line"], str(b["rows"]), fmt_usd(b["proceeds"]), fmt_usd(b["cost"]),
                                       fmt_gain(b["gain_loss"]))])
        return [
            data_table(rows, [0.4, 2.35, 0.65, 0.45, 1.05, 1.05, 1.05]),
            self.text("Each box is its own Form 8949 page, and its totals go on the Schedule D line shown: "
                      "the totals of the IRS forms BitcoinTX fills (Reports: IRS Reports).", self.styles.note),
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
        return story + [data_table(rows, [0.72, 0.72, 0.82, 0.38, 0.5, 0.86, 1.0, 1.0, 1.0], total=True)]

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
            return story + [self.nothing("income")]
        rows = [self.header("Received", "Source", "BTC", "Value (USD)", numbers_from=2)]
        rows += [[self.text(self.date(t.get("date", ""))), self.text(t.get("type", "")),
                  *self.numbers(fmt_btc(t.get("amount", 0.0)), fmt_usd(t.get("value_usd", 0.0)))]
                 for t in self.income]
        rows.append([self.total_label(), "", *self.numbers(
            fmt_btc(sum(t.get("amount", 0.0) for t in self.income)), fmt_usd(self.income_total()), bold=True)])
        return story + [data_table(rows, [1.4, 2.0, 1.8, 1.8], total=True)]

    # 4. Gifts, donations and lost coins
    def gifts_detail(self) -> list:
        story = self.section(4, "Gifts, donations and lost coins",
                             "Bitcoin given away, donated or lost. These are not sales, so they have no gain or loss "
                             "of their own; a network fee paid with them is a disposal (section 2).")
        if not self.gifts:
            return story + [self.nothing("gifts, donations or lost coins")]
        rows = [self.header("Date", "Kind", "BTC", "Fair market value", numbers_from=2)]
        for g in self.gifts:
            fmv = g.get("fmv_usd")
            rows.append([self.text(self.date(g.get("date", ""))), self.text(g.get("type", "")), *self.numbers(
                fmt_btc(g.get("amount", 0.0)), fmt_usd(fmv) if fmv is not None else "not given")])
        rows.append([self.total_label(), "", *self.numbers(
            fmt_btc(sum(g.get("amount", 0.0) for g in self.gifts)),
            fmt_usd(sum(g.get("fmv_usd") or 0.0 for g in self.gifts)), bold=True)])
        return story + [data_table(rows, [1.4, 2.0, 1.8, 1.8], total=True)]

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
        return data_table(rows, [1.2, 1.8, 1.4, 1.3, 1.3])

    # 6. Notes
    def notes(self) -> list:
        notes = (
            "All amounts are in US dollars unless marked BTC. Losses are shown in parentheses, as on the IRS forms.",
            "Capital gains use the first in, first out (FIFO) method within each account: a disposal uses the "
            "oldest bitcoin held in that account. Trading between BTC and USD is a taxable event.",
            "A disposal is long-term when the bitcoin was held more than one year (disposed of after the first "
            "anniversary of its acquisition); otherwise it is short-term.",
            "USD values are the ones entered with each transaction. A value left blank comes from that day's "
            "stored daily BTC price.",
            f"All dates are shown as MM/DD/YYYY (the IRS format) in the tax timezone ({self.tz_name}).",
            "A Form 8949 box follows what a broker reports on Form 1099-B or 1099-DA; a transaction's "
            "Broker form setting records what your broker's form actually showed.",
            "This report is prepared from your own records. It may be used for tax purposes after you, or "
            "your tax advisor, have checked it.",
        )
        return [
            *self.section(6, "Notes", "How the figures in this report are made."),
            *[Paragraph(pdf_text(note), self.styles.bullet, bulletText="•") for note in notes],
        ]
