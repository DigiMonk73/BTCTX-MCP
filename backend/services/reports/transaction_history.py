# FILE: backend/services/reports/transaction_history.py

"""
transaction_history.py

Generates a Transaction History Report for a given year (including partial data if it's the current year).
Exports either PDF or CSV, listing all Deposits, Withdrawals, Transfers, Buys, and Sells with relevant fields.

Key columns:
    - date
    - type
    - from_account
    - to_account
    - asset
    - amount
    - fee_amount
    - fee_currency
    - cost_basis_usd
    - proceeds_usd
    - realized_gain_usd
    - holding_period
    - description

We ensure:
  - All valid types (Deposit, Withdrawal, Transfer, Buy, Sell)
  - Strict date/time sort
  - "Transfers" included
  - Combined "Sell/Withdrawal" label for sells/withdrawals
  - "Income"/"Reward"/"Interest" for deposit with matching source
  - Decimal formatting: BTC => always 8 decimals, USD => 2 decimals

NOTE: This module is referenced by the /simple_transaction_history route in 'reports.py',
which directly calls generate_transaction_history_report(...) to bypass advanced cost-basis logic.
"""

import logging
from io import BytesIO
from decimal import Decimal
from typing import List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfgen.canvas import Canvas

from sqlalchemy.orm import Session
from backend.models.transaction import Transaction
from backend.models.account import Account

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Utility: Format decimals with different precision for BTC vs. USD
# -----------------------------------------------------------------------------
def _format_decimal(value: Optional[str], currency: str = "USD") -> str:
    """
    Returns a string with 8 decimal places if currency = BTC,
    otherwise 2 decimal places for fiat (default USD).
    If value is None or empty, returns '' (blank).
    """
    if not value:
        return ""
    dec_val = Decimal(value)
    if currency.upper() == "BTC":
        return f"{dec_val:.8f}"
    else:
        # default fiat formatting => 2 decimals
        return f"{dec_val:.2f}"


def generate_transaction_history_report(
    db: Session,
    year: int,
    format: str = "pdf"
) -> bytes:
    """
    High-level function to generate the Transaction History for a given year in PDF or CSV.

    1) Queries all transactions of [Deposit, Withdrawal, Transfer, Buy, Sell] within the year range.
       - If it's the current year, fetch up to "today" (year-to-date).
       - Otherwise, fetch up to Dec 31 of that year.
    2) Depending on 'format':
       - "pdf": calls _generate_pdf(...)
       - "csv": calls _generate_csv(...)
    3) Returns the resulting bytes (PDF) or CSV bytes (utf-8).
    """

    # Tax-year range in the user's tax timezone (see services/tax_time.py)
    from backend.services.tax_time import get_tax_timezone, tax_year_bounds
    start_of_year, end_of_year = tax_year_bounds(year, get_tax_timezone(db))

    # Fetch transactions of valid types, strictly sorted
    valid_types = ["Deposit", "Withdrawal", "Transfer", "Buy", "Sell"]
    txs = (
        db.query(Transaction)
        .filter(
            Transaction.type.in_(valid_types),
            Transaction.timestamp >= start_of_year,
            Transaction.timestamp < end_of_year
        )
        .order_by(Transaction.timestamp.asc(), Transaction.id.asc())
        .all()
    )

    logger.info(
        "DEBUG: Found %d transactions for year=%d in date range [%s -> %s].",
        len(txs), year, start_of_year, end_of_year
    )

    # Build intermediate row data (accounts fetched once — avoids per-row queries)
    accounts = {a.id: a for a in db.query(Account).all()}
    results = []
    for tx in txs:
        row = _build_row(accounts, tx)
        logger.debug("DEBUG: Built row for Tx ID=%s => %s", tx.id, row)
        results.append(row)

    # Output as CSV or PDF
    if format.lower() == "csv":
        csv_data = _generate_csv(results, year)
        return csv_data.encode("utf-8")
    else:
        pdf_bytes = _generate_pdf(results, year)
        return pdf_bytes


def _build_row(accounts: dict, tx: Transaction) -> dict:
    """
    Produces a dict with our final columns:
      date, type, from_account, to_account, asset, amount,
      fee_amount, fee_currency, cost_basis_usd, proceeds_usd,
      realized_gain_usd, holding_period, description
    """
    # ISO 8601 date/time
    dt_str = tx.timestamp.isoformat()

    # Combined transaction type
    csv_type = _map_tx_type(tx)

    # Resolve accounts
    from_acct = _get_account_name(accounts, tx.from_account_id)
    to_acct = _get_account_name(accounts, tx.to_account_id)

    # Determine asset
    csv_asset = _determine_asset(accounts, tx)

    # Format amounts
    amount_str = _format_decimal(tx.amount, currency=csv_asset)
    fee_amt_str = _format_decimal(tx.fee_amount, currency=(tx.fee_currency or "USD"))
    fee_cur_str = tx.fee_currency or ""

    # Cost basis, proceeds, realized gain => USD with 2 decimals
    cost_basis_str = _format_decimal(tx.cost_basis_usd, "USD") if tx.cost_basis_usd else ""
    proceeds_str = _format_decimal(tx.proceeds_usd, "USD") if tx.proceeds_usd else ""
    realized_gain_str = _format_decimal(tx.realized_gain_usd, "USD") if tx.realized_gain_usd else ""

    # Holding period => short/long (if any)
    hold_str = tx.holding_period or ""

    # Description logic
    desc_str = _map_description(tx)

    return {
        "date": dt_str,
        "type": csv_type,
        "from_account": from_acct,
        "to_account": to_acct,
        "asset": csv_asset,
        "amount": amount_str,
        "fee_amount": fee_amt_str,
        "fee_currency": fee_cur_str,
        "cost_basis_usd": cost_basis_str,
        "proceeds_usd": proceeds_str,
        "realized_gain_usd": realized_gain_str,
        "holding_period": hold_str,
        "description": desc_str,
    }


def _map_tx_type(tx: Transaction) -> str:
    """
    - (Deposit && source=Income)  => "Income"
    - (Deposit && source=Reward)  => "Reward"
    - (Deposit && source=Interest)=> "Interest"
    - else if Deposit => "Deposit"
    - If Sell or Withdrawal => "Sell/Withdrawal"
    - If Transfer => "Transfer"
    - If Buy => "Buy"
    """
    logger.debug("DEBUG: _map_tx_type called for Tx ID=%s, type=%s, source=%s", tx.id, tx.type, tx.source)
    t = tx.type
    if t == "Deposit":
        s = (tx.source or "").lower()
        if s == "income":
            return "Income"
        elif s == "reward":
            return "Reward"
        elif s == "interest":
            return "Interest"
        else:
            return "Deposit"
    elif t in ["Sell", "Withdrawal"]:
        return "Sell/Withdrawal"
    elif t == "Transfer":
        return "Transfer"
    elif t == "Buy":
        return "Buy"
    return t  # fallback if unexpected


def _determine_asset(accounts: dict, tx: Transaction) -> str:
    """
    Determine the transaction currency based on the type & account currency:
      - Deposit => to_acct currency
      - Withdrawal/Sell => from_acct currency
      - Buy => to_acct currency
      - Transfer => from_acct currency (assuming same currency on both)
    """
    from_acct = accounts.get(tx.from_account_id)
    to_acct = accounts.get(tx.to_account_id)

    if tx.type == "Deposit":
        return to_acct.currency if (to_acct and to_acct.currency) else "BTC"
    elif tx.type in ("Withdrawal", "Sell"):
        return from_acct.currency if (from_acct and from_acct.currency) else "BTC"
    elif tx.type == "Buy":
        return to_acct.currency if (to_acct and to_acct.currency) else "BTC"
    elif tx.type == "Transfer":
        return from_acct.currency if (from_acct and from_acct.currency) else "BTC"
    return "BTC"


def _map_description(tx: Transaction) -> str:
    """
    If Sell/Withdrawal => "CapitalGainsTransaction" if realized_gain_usd != 0
    If Deposit => source
    Otherwise => purpose
    """
    logger.debug("DEBUG: _map_description for Tx ID=%s, type=%s, realized_gain_usd=%s",
                 tx.id, tx.type, tx.realized_gain_usd)
    if tx.type in ["Sell", "Withdrawal"]:
        if tx.realized_gain_usd and Decimal(tx.realized_gain_usd) != 0:
            return "CapitalGainsTransaction"
        return tx.purpose or ""
    elif tx.type == "Deposit":
        return tx.source or ""
    return tx.purpose or ""


def _get_account_name(accounts: dict, account_id: int) -> str:
    """
    Convert account_id to a user-friendly name.
    If account_id=99 => "External", else look up the prefetched accounts dict.
    """
    if not account_id:
        return ""
    if account_id == 99:
        return "External"
    acct = accounts.get(account_id)
    if acct:
        return acct.name or ""
    return ""


# --------------------------------------------------------------------------------
# CSV / PDF Generators
# --------------------------------------------------------------------------------

def _generate_csv(rows: List[dict], year: int) -> str:
    """
    Build CSV data with columns:
      date,type,from_account,to_account,asset,amount,
      fee_amount,fee_currency,cost_basis_usd,proceeds_usd,
      realized_gain_usd,holding_period,description
    """
    headers = [
        "date",
        "type",
        "from_account",
        "to_account",
        "asset",
        "amount",
        "fee_amount",
        "fee_currency",
        "cost_basis_usd",
        "proceeds_usd",
        "realized_gain_usd",
        "holding_period",
        "description",
    ]
    lines = [",".join(headers)]

    logger.info("DEBUG: Starting _generate_csv with %d rows for year=%s", len(rows), year)

    for idx, r in enumerate(rows):
        line_elems = [
            _escape_csv(r["date"]),
            _escape_csv(r["type"]),
            _escape_csv(r["from_account"]),
            _escape_csv(r["to_account"]),
            _escape_csv(r["asset"]),
            _escape_csv(r["amount"]),
            _escape_csv(r["fee_amount"]),
            _escape_csv(r["fee_currency"]),
            _escape_csv(r["cost_basis_usd"]),
            _escape_csv(r["proceeds_usd"]),
            _escape_csv(r["realized_gain_usd"]),
            _escape_csv(r["holding_period"]),
            _escape_csv(r["description"]),
        ]
        final_line = ",".join(line_elems)
        logger.debug("DEBUG: CSV row #%d => %s", idx + 1, final_line)
        lines.append(final_line)

    csv_data = "\n".join(lines)
    logger.info(f"Generated Transaction History CSV for {year}, {len(rows)} rows.")
    return csv_data


def _escape_csv(val: str) -> str:
    """
    Minimal CSV escaping: wrap in quotes if there's a comma or quote.
    Double any existing quotes.
    """
    logger.debug("DEBUG: _escape_csv input=%r", val)
    if not val:
        return ""
    need_quotes = ("," in val) or ('"' in val)
    escaped = val.replace('"', '""')
    if need_quotes:
        return f"\"{escaped}\""
    return escaped


def _generate_pdf(rows: List[dict], year: int) -> bytes:
    """
    Build a PDF from the row dicts with columns:
      date, type, from_account, to_account, asset, amount,
      fee_amount, fee_currency, cost_basis_usd, proceeds_usd,
      realized_gain_usd, holding_period, description
    """

    buffer = BytesIO()
    styles = getSampleStyleSheet()

    heading_style = ParagraphStyle(
        name="Heading1Left",
        parent=styles["Heading1"],
        alignment=0,
        spaceBefore=12,
        spaceAfter=8,
    )
    normal_style = styles["Normal"]
    wrapped_style = ParagraphStyle(
        name="Wrapped",
        parent=normal_style,
        fontSize=8,
        leading=10,
        wordWrap="CJK",
    )

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    def on_first_page(canvas: Canvas, doc_obj):
        pass

    def on_later_pages(canvas: Canvas, doc_obj):
        page_num = doc_obj.page
        canvas.setFont("Helvetica", 9)
        canvas.drawString(0.5 * inch, 0.5 * inch, "Generated by BitcoinTX")
        canvas.drawRightString(7.5 * inch, 0.5 * inch, f"Page {page_num}")

    story = []

    # Title
    story.append(Paragraph(f"Transaction History for {year}", heading_style))
    story.append(Spacer(1, 0.2 * inch))

    if not rows:
        story.append(Paragraph("No transactions found for this period.", normal_style))
        doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        logger.info(f"Generated empty Transaction History PDF for {year}.")
        return pdf_bytes

    # Table header
    data = [[
        "date",
        "type",
        "from_account",
        "to_account",
        "asset",
        "amount",
        "fee_amount",
        "fee_currency",
        "cost_basis_usd",
        "proceeds_usd",
        "realized_gain_usd",
        "holding_period",
        "description",
    ]]

    logger.info("DEBUG: Building PDF table with %d rows for year=%s", len(rows), year)

    # Add table rows
    for idx, r in enumerate(rows):
        row_data = [
            Paragraph(r["date"], wrapped_style),
            Paragraph(r["type"], wrapped_style),
            Paragraph(r["from_account"], wrapped_style),
            Paragraph(r["to_account"], wrapped_style),
            Paragraph(r["asset"], wrapped_style),
            Paragraph(r["amount"], wrapped_style),
            Paragraph(r["fee_amount"], wrapped_style),
            Paragraph(r["fee_currency"], wrapped_style),
            Paragraph(r["cost_basis_usd"], wrapped_style),
            Paragraph(r["proceeds_usd"], wrapped_style),
            Paragraph(r["realized_gain_usd"], wrapped_style),
            Paragraph(r["holding_period"], wrapped_style),
            Paragraph(r["description"], wrapped_style),
        ]
        data.append(row_data)
        logger.debug("DEBUG: PDF row #%d => %s", idx + 1, r)

    # Adjust column widths
    col_widths = [
        1.2 * inch,  # date
        0.9 * inch,  # type
        1.0 * inch,  # from_account
        1.0 * inch,  # to_account
        0.6 * inch,  # asset
        0.9 * inch,  # amount
        0.9 * inch,  # fee_amount
        0.7 * inch,  # fee_currency
        1.0 * inch,  # cost_basis_usd
        0.9 * inch,  # proceeds_usd
        1.0 * inch,  # realized_gain_usd
        0.9 * inch,  # holding_period
        1.2 * inch,  # description
    ]
    table = Table(data, colWidths=col_widths)
    table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))

    story.append(table)
    story.append(Spacer(1, 0.3 * inch))

    story.append(Paragraph(
        "All amounts, fees, and cost data are shown as recorded in BitcoinTX. "
        "For official tax usage, please consult your accountant.",
        normal_style
    ))

    doc.build(story, onFirstPage=on_first_page, onLaterPages=on_later_pages)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    logger.info(f"Generated Transaction History PDF for {year}, {len(rows)} rows.")
    return pdf_bytes
