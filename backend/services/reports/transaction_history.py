"""
The transaction history of one tax year, as CSV or PDF: every Deposit,
Withdrawal, Transfer, Buy and Sell in time order, with its accounts,
amounts, fee, USD values and gain as stored (BTC to 8 decimal places, USD
to 2). An income deposit shows as its source (Income, Reward, Interest), a
Sell or Withdrawal as "Sell/Withdrawal".
"""

import logging
from decimal import Decimal
from io import BytesIO

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from sqlalchemy.orm import Session

from backend.constants import ACCOUNT_EXTERNAL
from backend.models.account import Account
from backend.models.transaction import Transaction
from backend.services.reports.pdf_layout import ReportStyles, grid_table
from backend.services.reports.safe_text import csv_text, pdf_text
from backend.services.tax_time import get_tax_timezone, tax_year_bounds

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
    return _generate_pdf(rows, year)


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


def _generate_pdf(rows: list[dict], year: int) -> bytes:
    styles = ReportStyles()
    story = [Paragraph(f"Transaction History for {pdf_text(year)}", styles.heading), Spacer(1, 0.2 * inch)]
    if rows:
        # Ledger text is shown as written, never read as markup (safe_text.py)
        cells = [[Paragraph(pdf_text(row[col]), styles.cell) for col in COLUMNS] for row in rows]
        story += [
            grid_table([list(COLUMNS)] + cells, list(COLUMN_WIDTHS.values()), align="LEFT"),
            Spacer(1, 0.3 * inch),
            Paragraph(DISCLAIMER, styles.normal),
        ]
    else:
        story.append(Paragraph("No transactions found for this period.", styles.normal))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    # The first page has no footer.
    doc.build(story, onLaterPages=_footer)
    if rows:
        logger.debug(f"Generated Transaction History PDF for {year}, {len(rows)} rows.")
    else:
        logger.info(f"Generated empty Transaction History PDF for {year}.")
    return buffer.getvalue()


def _footer(canvas: Canvas, doc) -> None:
    canvas.setFont("Helvetica", 9)
    canvas.drawString(0.5 * inch, 0.5 * inch, "Generated by BitcoinTX")
    canvas.drawRightString(7.5 * inch, 0.5 * inch, f"Page {doc.page}")
