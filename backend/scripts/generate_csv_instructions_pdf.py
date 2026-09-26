#!/usr/bin/env python3
"""
Generate CSV Import Instructions PDF using ReportLab.

This script creates a static PDF file with instructions for using the
CSV import feature in BitcoinTX. Run this script whenever the content
needs to be updated.

Usage:
    python backend/scripts/generate_csv_instructions_pdf.py

Output:
    backend/assets/csv_import_instructions.pdf
"""

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, PageBreak
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def generate_csv_instructions_pdf():
    """Generate the CSV import instructions PDF."""

    # Output path
    output_dir = Path(__file__).parent.parent / "assets"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "csv_import_instructions.pdf"

    # Create document
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    # Styles
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        name="Title",
        parent=styles["Title"],
        fontSize=24,
        spaceAfter=20,
    )

    heading1_style = ParagraphStyle(
        name="Heading1Custom",
        parent=styles["Heading1"],
        fontSize=16,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor("#333333"),
    )

    heading2_style = ParagraphStyle(
        name="Heading2Custom",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=15,
        spaceAfter=8,
        textColor=colors.HexColor("#444444"),
    )

    normal_style = ParagraphStyle(
        name="NormalCustom",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=8,
    )

    bullet_style = ParagraphStyle(
        name="Bullet",
        parent=normal_style,
        leftIndent=20,
        bulletIndent=10,
        spaceAfter=4,
    )

    code_style = ParagraphStyle(
        name="Code",
        parent=normal_style,
        fontName="Courier",
        fontSize=9,
        leftIndent=20,
        backColor=colors.HexColor("#f5f5f5"),
        borderPadding=5,
    )

    warning_style = ParagraphStyle(
        name="Warning",
        parent=normal_style,
        backColor=colors.HexColor("#fff3cd"),
        borderPadding=10,
        borderColor=colors.HexColor("#ffc107"),
        borderWidth=1,
        spaceBefore=10,
        spaceAfter=10,
    )

    # Table styles
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8.5, leading=10.5)

    def wrap_cells(rows):
        """Body cells as Paragraphs so long text wraps inside its column."""
        return [rows[0]] + [[Paragraph(str(c).replace("\n", "<br/>"), cell_style) for c in row] for row in rows[1:]]

    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#4a4a4a")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f9f9f9")),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ])

    # Build content
    story = []

    # === Title ===
    story.append(Paragraph("BitcoinTX CSV Import Guide", title_style))
    story.append(Spacer(1, 10))

    # === Overview ===
    story.append(Paragraph("Overview", heading1_style))
    story.append(Paragraph(
        "The CSV Import feature allows you to bulk-import your Bitcoin transaction history "
        "into BitcoinTX. This is useful for:",
        normal_style
    ))
    story.append(Paragraph("• Setting up a new installation with existing data", bullet_style))
    story.append(Paragraph("• Migrating from another tracking system", bullet_style))
    story.append(Paragraph("• Restoring from a CSV backup", bullet_style))

    story.append(Paragraph(
        "<b>Important:</b> The database must be empty before importing. "
        "This ensures clean FIFO cost basis calculations. If you have existing "
        "transactions, delete them first from the Settings page.",
        warning_style
    ))

    # === Quick Start Guide ===
    story.append(Paragraph("Quick Start Guide", heading1_style))

    story.append(Paragraph("Step 1: Download the Template", heading2_style))
    story.append(Paragraph(
        "Go to Settings → Data Management and click \"Download Template\". "
        "This gives you a CSV file with the correct column headers and sample rows.",
        normal_style
    ))

    story.append(Paragraph("Step 2: Fill in Your Data", heading2_style))
    story.append(Paragraph(
        "Open the template in a spreadsheet application (Excel, Google Sheets, etc.) "
        "and replace the sample rows with your actual transaction data. "
        "Delete any sample rows you don't need.",
        normal_style
    ))

    story.append(Paragraph("Step 3: Preview the Import", heading2_style))
    story.append(Paragraph(
        "Upload your CSV file and click \"Preview\". The system validates all rows and "
        "shows you any errors or warnings. Fix any issues before proceeding.",
        normal_style
    ))

    story.append(Paragraph("Step 4: Execute the Import", heading2_style))
    story.append(Paragraph(
        "If the preview shows no errors, click \"Import\" to create all transactions. "
        "The import is atomic – if anything fails, no transactions are created.",
        normal_style
    ))

    # === Field Reference ===
    story.append(PageBreak())
    story.append(Paragraph("Field Reference", heading1_style))

    story.append(Paragraph("CSV Columns", heading2_style))

    columns_data = [
        ["Column", "Required", "Description"],
        ["date", "Yes", "Date/time (ISO8601 preferred). Without a timezone it is in your tax timezone (Settings); a date alone means noon"],
        ["type", "Yes", "Transaction type: Deposit, Withdrawal, Transfer, Buy, Sell"],
        ["amount", "Yes", "BTC (up to 8 decimals), or USD for Bank/Exchange USD rows. Transfer: what left the account, fee included. Withdrawal: what the recipient got, fee on top"],
        ["from_account", "Yes", "Source account name"],
        ["to_account", "Yes", "Destination account name"],
        ["cost_basis_usd", "Conditional", "Buy: USD paid for the BTC, before the fee (the fee column is added to the basis). Deposit: optional; Income/Interest/Reward blank = that day's value"],
        ["proceeds_usd", "Conditional", "Sell: gross USD, before the fee (the fee is subtracted). Spent withdrawal: value received; blank = that day's value"],
        ["fee_amount", "No", "Fee amount (never also included in cost_basis_usd or proceeds_usd)"],
        ["fee_currency", "No", "USD for Buy/Sell and moves out of Bank/Exchange USD; BTC for moves out of Wallet/Exchange BTC"],
        ["source", "No", "For Deposits: N/A, MyBTC, Gift, Income, Interest, Reward"],
        ["purpose", "Conditional", "For Withdrawals: Spent, Gift, Donation, Lost"],
        ["notes", "No", "Optional notes (not imported, for your reference only)"],
    ]

    col_table = Table(wrap_cells(columns_data), colWidths=[1.3*inch, 0.9*inch, 4.5*inch])
    col_table.setStyle(table_style)
    story.append(col_table)

    # === Valid Values ===
    story.append(Paragraph("Transaction Types", heading2_style))

    types_data = [
        ["Type", "Description"],
        ["Deposit", "BTC entering your portfolio (purchase, gift received, income, etc.)"],
        ["Withdrawal", "BTC leaving your portfolio (spent, gift sent, donation, loss)"],
        ["Transfer", "Moving BTC between your own wallets (no taxable event)"],
        ["Buy", "Purchasing BTC on an exchange with USD"],
        ["Sell", "Selling BTC on an exchange for USD"],
    ]

    types_table = Table(types_data, colWidths=[1.3*inch, 5.4*inch])
    types_table.setStyle(table_style)
    story.append(types_table)

    story.append(Paragraph("Account Names", heading2_style))

    accounts_data = [
        ["Account", "Description"],
        ["Bank", "Your fiat bank account (USD)"],
        ["Wallet", "Your self-custody Bitcoin wallet"],
        ["Exchange USD", "USD balance on an exchange"],
        ["Exchange BTC", "BTC balance on an exchange"],
        ["External", "Outside your portfolio (source for deposits, destination for withdrawals)"],
    ]

    accounts_table = Table(accounts_data, colWidths=[1.5*inch, 5.2*inch])
    accounts_table.setStyle(table_style)
    story.append(accounts_table)

    story.append(Paragraph("Source Values (for Deposits)", heading2_style))

    source_data = [
        ["Value", "Description"],
        ["N/A", "Not applicable or unspecified"],
        ["MyBTC", "BTC you already owned (transferring in)"],
        ["Gift", "Received as a gift"],
        ["Income", "Payment for goods/services"],
        ["Interest", "Earned as interest"],
        ["Reward", "Mining, staking, or other rewards"],
    ]

    source_table = Table(source_data, colWidths=[1.3*inch, 5.4*inch])
    source_table.setStyle(table_style)
    story.append(source_table)

    story.append(Paragraph("Purpose Values (for Withdrawals)", heading2_style))

    purpose_data = [
        ["Value", "Description"],
        ["Spent", "Used to purchase goods/services (taxable sale)"],
        ["Gift", "Given as a gift"],
        ["Donation", "Donated to charity"],
        ["Lost", "Lost or stolen BTC"],
    ]

    purpose_table = Table(purpose_data, colWidths=[1.3*inch, 5.4*inch])
    purpose_table.setStyle(table_style)
    story.append(purpose_table)

    # === Account Rules ===
    story.append(PageBreak())
    story.append(Paragraph("Account Rules by Transaction Type", heading1_style))
    story.append(Paragraph(
        "Each transaction type has specific account requirements. "
        "The system enforces these rules during validation.",
        normal_style
    ))

    rules_data = [
        ["Type", "From Account", "To Account", "Required Fields"],
        ["Deposit", "External", "Wallet or\nExchange BTC", "cost_basis_usd (optional, defaults to $0)"],
        ["Withdrawal", "Wallet or\nExchange BTC", "External", "purpose required;\nproceeds_usd for \"Spent\""],
        ["Transfer", "Any account", "Another account,\nsame currency", "Fee in the sending account's currency;\naccounts must be different"],
        ["Buy", "Bank or\nExchange USD", "Exchange BTC", "cost_basis_usd required;\nfee must be USD"],
        ["Sell", "Exchange BTC", "Exchange USD", "proceeds_usd required;\nfee must be USD"],
    ]

    rules_table = Table(wrap_cells(rules_data), colWidths=[1.0*inch, 1.3*inch, 1.3*inch, 3.1*inch])
    rules_table.setStyle(table_style)
    story.append(rules_table)

    # === Date Formats ===
    story.append(Paragraph("Supported Date Formats", heading1_style))
    story.append(Paragraph(
        "The following date formats are accepted. ISO8601 with timezone is recommended. "
        "A date or time without a timezone is read in your tax timezone (Settings), and a "
        "date alone means noon that day, so it stays in the right tax year:",
        normal_style
    ))

    date_data = [
        ["Format", "Example"],
        ["ISO8601 with Z (preferred)", "2024-01-15T10:30:00Z"],
        ["ISO8601 with timezone", "2024-01-15T10:30:00+00:00"],
        ["ISO8601 without timezone", "2024-01-15T10:30:00"],
        ["Date with time", "2024-01-15 10:30:00"],
        ["Date only", "2024-01-15"],
        ["US format with time", "01/15/2024 10:30:00"],
        ["US format date only", "01/15/2024"],
    ]

    date_table = Table(date_data, colWidths=[2.5*inch, 2.5*inch])
    date_table.setStyle(table_style)
    story.append(date_table)

    # === Examples ===
    story.append(PageBreak())
    story.append(Paragraph("Example Rows", heading1_style))
    story.append(Paragraph(
        "Below are example CSV rows for each transaction type. "
        "Use these as templates for your own data.",
        normal_style
    ))

    story.append(Paragraph("Buy from Exchange USD:", heading2_style))
    story.append(Paragraph(
        "2024-01-15T10:30:00Z,Buy,0.012,Exchange USD,Exchange BTC,500.00,,5.00,USD,,,",
        code_style
    ))

    story.append(Paragraph("Buy from Bank (auto-buy):", heading2_style))
    story.append(Paragraph(
        "2024-01-20T08:00:00Z,Buy,0.05,Bank,Exchange BTC,2500.00,,10.00,USD,,,",
        code_style
    ))

    story.append(Paragraph("Sell (selling BTC on exchange):", heading2_style))
    story.append(Paragraph(
        "2024-02-15T11:30:00Z,Sell,0.3,Exchange BTC,Exchange USD,,15000.00,10.00,USD,,,",
        code_style
    ))

    story.append(Paragraph("Deposit (BTC entering your wallet):", heading2_style))
    story.append(Paragraph(
        "2024-01-20T14:00:00Z,Deposit,0.5,External,Wallet,21000.00,,,Income,,",
        code_style
    ))

    story.append(Paragraph("Withdrawal (spending BTC):", heading2_style))
    story.append(Paragraph(
        "2024-03-01T09:00:00Z,Withdrawal,0.1,Wallet,External,,5500.00,,,Spent,",
        code_style
    ))

    story.append(Paragraph("Transfer (moving between wallets):", heading2_style))
    story.append(Paragraph(
        "2024-02-01T16:45:00Z,Transfer,1.0,Exchange BTC,Wallet,,,0.0001,BTC,,,",
        code_style
    ))

    # === Troubleshooting ===
    story.append(Paragraph("Troubleshooting", heading1_style))

    story.append(Paragraph("Common Errors", heading2_style))

    errors_data = [
        ["Error", "Solution"],
        ["\"Database has X existing transactions\"", "Delete all transactions from Settings before importing"],
        ["\"Invalid transaction type\"", "Use exactly: Deposit, Withdrawal, Transfer, Buy, or Sell"],
        ["\"Invalid account name\"", "Use exactly: Bank, Wallet, Exchange USD, Exchange BTC, or External"],
        ["\"cost_basis_usd required for Buy\"", "Add the USD paid for the BTC, before the fee"],
        ["\"proceeds_usd required for Sell\"", "Add the gross USD, before the fee"],
        ["\"purpose required for Withdrawal\"", "Add purpose: Spent, Gift, Donation, or Lost"],
        ["\"Invalid accounts for Buy\"", "Buy must be: from Bank or Exchange USD, to Exchange BTC"],
        ["\"Invalid accounts for Sell\"", "Sell must be: from Exchange BTC, to Exchange USD"],
        ["\"Invalid accounts for Deposit\"", "Deposit must be: from External, to Wallet or Exchange BTC"],
        ["\"Cannot transfer to same account\"", "Transfer requires different source and destination"],
    ]

    errors_table = Table(errors_data, colWidths=[2.8*inch, 3.9*inch])
    errors_table.setStyle(table_style)
    story.append(errors_table)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "<b>Tip:</b> Use the Preview feature to validate your CSV before importing. "
        "Fix all errors shown in red before clicking Import.",
        warning_style
    ))

    # === Footer ===
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "Generated by BitcoinTX • For more help, visit the project repository",
        ParagraphStyle(
            name="Footer",
            parent=normal_style,
            alignment=1,  # Center
            textColor=colors.gray,
        )
    ))

    # Build PDF
    doc.build(story)
    print(f"PDF generated: {output_path}")
    return output_path


if __name__ == "__main__":
    generate_csv_instructions_pdf()
