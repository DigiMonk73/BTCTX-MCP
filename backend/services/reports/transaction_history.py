"""
The transaction history of one tax year, as CSV or PDF: every Deposit,
Withdrawal, Transfer, Buy and Sell in time order, with its accounts,
amounts, fee, USD values and gain as stored (BTC to 8 decimal places, USD
to 2). In the CSV an income deposit shows as its source (Income, Reward,
Interest), a Sell or Withdrawal as "Sell/Withdrawal". The PDF is a
landscape table in the complete tax report's look (pdf_layout.py): dates
in the tax timezone, each type with its source or purpose.
"""

import logging
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_EXTERNAL
from backend.models.account import Account
from backend.models.transaction import Transaction
from backend.services.reports.pdf_layout import (
    ReportStyles, data_table, draw_footer_note, draw_running_header, numbered_canvas,
)
from backend.services.reports.safe_text import csv_text, pdf_text
from backend.services.tax_time import format_tax_date, get_tax_timezone, tax_year_bounds

logger = logging.getLogger(__name__)

# The report's columns, in order, with their PDF widths in inches.
COLUMN_WIDTHS = {
    "date": 1.2,
    "type": 0.9,
    "from_account": 1.0,
    "to_account": 1.0,
    "asset": 0.6,
    "amount": 0.9,
    "fee_amount": 0.9,
    "fee_currency": 0.7,
    "cost_basis_usd": 1.0,
    "proceeds_usd": 0.9,
    "realized_gain_usd": 1.0,
    "holding_period": 0.9,
    "description": 1.2,
}
COLUMNS = list(COLUMN_WIDTHS)
NUMBER_COLUMNS = {"amount", "fee_amount", "cost_basis_usd", "proceeds_usd", "realized_gain_usd"}

TYPES = ["Deposit", "Withdrawal", "Transfer", "Buy", "Sell"]
INCOME_SOURCES = {"income": "Income", "reward": "Reward", "interest": "Interest"}

DISCLAIMER = (
    "All amounts, fees, and cost data are shown as recorded in BitcoinTX. "
    "For official tax usage, please consult your accountant."
)
# The PDF's columns: heading, the row's cell, width in inches (9.5 in all)
PDF_COLUMNS = (
    ("Date", "_date", 0.8), ("Type", "_kind", 1.35), ("From", "from_account", 0.95), ("To", "to_account", 0.95),
    ("Amount", "_amount", 1.2), ("Fee", "_fee", 1.0), ("Cost basis", "cost_basis_usd", 0.9),
    ("Proceeds", "proceeds_usd", 0.9), ("Gain (loss)", "realized_gain_usd", 0.9), ("Term", "holding_period", 0.55),
)
PDF_NUMBER_COLUMNS = range(4, 9)  # Amount to Gain (loss), right-aligned
FOOTER_NOTE = "Prepared with BitcoinTX from your own records. Check it with your tax advisor before filing."


def generate_transaction_history_report(db: Session, year: int, format: str = "pdf") -> bytes:
    """The tax year's transactions (its bounds in the tax timezone) as a PDF,
    or as CSV when `format` is "csv"."""
    start_of_year, end_of_year = tax_year_bounds(year, get_tax_timezone(db))
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.type.in_(TYPES),
            Transaction.timestamp >= start_of_year,
            Transaction.timestamp < end_of_year
        )
        .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
        .all()
    )
    logger.debug(
        "Found %d transactions for year=%d in date range [%s -> %s].",
        len(txs), year, start_of_year, end_of_year
    )
    accounts = {a.id: a for a in db.query(Account).all()}
    rows = [_build_row(accounts, tx) for tx in txs]
    if format.lower() == "csv":
        return _generate_csv(rows, year).encode("utf-8")
    tz = get_tax_timezone(db)
    return _generate_pdf([{**row, **_pdf_cells(tx, row, tz)} for row, tx in zip(rows, txs)], year, str(tz))


def _pdf_cells(tx: Transaction, row: dict, tz) -> dict:
    """The PDF's own cells (the CSV keeps the stored values): the date in the
    tax timezone, the type with its source or purpose, amounts with their
    currency, USD values with thousands separators."""
    detail = tx.source if tx.type == "Deposit" else tx.purpose if tx.type == "Withdrawal" else None
    return {
        "_date": format_tax_date(tx.timestamp, tz),
        "_kind": f"{tx.type} ({detail})" if detail and detail != "N/A" else tx.type,
        "_amount": _with_currency(row["amount"], row["asset"]),
        "_fee": _with_currency(row["fee_amount"], row["fee_currency"]),
        **{col: f"{Decimal(row[col]):,.2f}" if row[col] else "" for col in
           ("cost_basis_usd", "proceeds_usd", "realized_gain_usd")},
        "holding_period": (row["holding_period"] or "").capitalize(),
    }


def _with_currency(value: str, currency: str) -> str:
    if not value:
        return ""
    return f"${Decimal(value):,.2f}" if currency == "USD" else f"{value} {currency}"


def _build_row(accounts: dict, tx: Transaction) -> dict:
    """The transaction's cells, by column."""
    asset = _determine_asset(accounts, tx)
    return {
        "date": tx.timestamp.isoformat(),
        "type": _map_tx_type(tx),
        "from_account": _get_account_name(accounts, tx.from_account_id),
        "to_account": _get_account_name(accounts, tx.to_account_id),
        "asset": asset,
        "amount": _format_decimal(tx.amount, currency=asset),
        "fee_amount": _format_decimal(tx.fee_amount, currency=(tx.fee_currency or "USD")),
        "fee_currency": tx.fee_currency or "",
        "cost_basis_usd": _format_decimal(tx.cost_basis_usd),
        "proceeds_usd": _format_decimal(tx.proceeds_usd),
        "realized_gain_usd": _format_decimal(tx.realized_gain_usd),
        "holding_period": tx.holding_period or "",
        "description": _map_description(tx),
    }


def _format_decimal(value, currency: str = "USD") -> str:
    """BTC to 8 decimal places, anything else to 2; blank for none or zero."""
    if not value:
        return ""
    places = 8 if currency.upper() == "BTC" else 2
    return f"{Decimal(value):.{places}f}"


def _map_tx_type(tx: Transaction) -> str:
    if tx.type == "Deposit":
        return INCOME_SOURCES.get((tx.source or "").lower(), "Deposit")
    if tx.type in ("Sell", "Withdrawal"):
        return "Sell/Withdrawal"
    return tx.type


def _determine_asset(accounts: dict, tx: Transaction) -> str:
    """The currency that moved: the receiving account's for a Deposit or Buy,
    the sending account's for a Withdrawal, Sell or Transfer."""
    if tx.type in ("Deposit", "Buy"):
        account = accounts.get(tx.to_account_id)
    elif tx.type in ("Withdrawal", "Sell", "Transfer"):
        account = accounts.get(tx.from_account_id)
    else:
        return "BTC"
    return account.currency if (account and account.currency) else "BTC"


def _map_description(tx: Transaction) -> str:
    """"CapitalGainsTransaction" for a disposal with a gain or loss; else a
    Deposit's source, or the purpose."""
    if tx.type in ("Sell", "Withdrawal") and tx.realized_gain_usd and Decimal(tx.realized_gain_usd) != 0:
        return "CapitalGainsTransaction"
    if tx.type == "Deposit":
        return tx.source or ""
    return tx.purpose or ""


def _get_account_name(accounts: dict, account_id: int) -> str:
    if not account_id:
        return ""
    if account_id == ACCOUNT_EXTERNAL:  # an id with no account row
        return "External"
    account = accounts.get(account_id)
    return (account.name or "") if account else ""


def _generate_csv(rows: list[dict], year: int) -> str:
    lines = [",".join(COLUMNS)]
    for row in rows:
        # Text cells can't start a spreadsheet formula; numbers stay numbers
        cells = [_escape_csv(row[col] if col in NUMBER_COLUMNS else csv_text(row[col])) for col in COLUMNS]
        lines.append(",".join(cells))
    logger.debug(f"Generated Transaction History CSV for {year}, {len(rows)} rows.")
    return "\n".join(lines)


def _escape_csv(value: str) -> str:
    """Quoted, with its quotes doubled, when it holds a comma or a quote."""
    if not value:
        return ""
    escaped = value.replace('"', '""')
    return f'"{escaped}"' if ("," in value or '"' in value) else escaped


def _generate_pdf(rows: list[dict], year: int, tz_name: str) -> bytes:
    styles = ReportStyles()
    # Ledger text is shown as written, never read as markup (safe_text.py)
    story = [
        Paragraph(f"TAX YEAR {pdf_text(year)}", styles.kicker),
        Spacer(1, 4),
        Paragraph("Transaction History", styles.heading),
        Paragraph(pdf_text(f"Every transaction of the year in time order, as recorded. Dates in the tax "
                           f"timezone ({tz_name}); amounts in USD unless marked BTC."), styles.intro),
    ]
    if rows:
        header = [Paragraph(title, styles.head_number if i in PDF_NUMBER_COLUMNS else styles.head)
                  for i, (title, _, _) in enumerate(PDF_COLUMNS)]
        cells = [[Paragraph(pdf_text(row[key]), styles.number if i in PDF_NUMBER_COLUMNS else styles.cell)
                  for i, (_, key, _) in enumerate(PDF_COLUMNS)] for row in rows]
        story += [data_table([header] + cells, [width for _, _, width in PDF_COLUMNS]),
                  Spacer(1, 0.2 * inch), Paragraph(DISCLAIMER, styles.note)]
    else:
        story.append(Paragraph(f"No transactions in {pdf_text(year)}.", styles.normal))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(letter), leftMargin=0.75 * inch, rightMargin=0.75 * inch,
                            topMargin=0.9 * inch, bottomMargin=0.95 * inch, title=f"{year} Transaction History",
                            author="BitcoinTX")
    doc.build(story, onFirstPage=_chrome(year), onLaterPages=_chrome(year), canvasmaker=numbered_canvas())
    if rows:
        logger.debug(f"Generated Transaction History PDF for {year}, {len(rows)} rows.")
    else:
        logger.info(f"Generated empty Transaction History PDF for {year}.")
    return buffer.getvalue()


def _chrome(year: int):
    def draw(canvas, doc) -> None:
        draw_running_header(canvas, f"{year} Transaction History")
        draw_footer_note(canvas, FOOTER_NOTE)
    return draw
