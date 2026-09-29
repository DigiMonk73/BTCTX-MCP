#!/usr/bin/env python3
"""
Writes backend/assets/csv_import_instructions.pdf, the CSV import guide the
app serves (GET /api/import/instructions). Run it after changing the guide:

    python backend/scripts/generate_csv_instructions_pdf.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

COLUMNS = [
    ["Column", "Required", "Description"],
    ["date", "Yes", "Date/time (ISO8601 preferred). Without a timezone it is in your tax timezone (Settings); a date alone means noon"],
    ["type", "Yes", "Transaction type: Deposit, Withdrawal, Transfer, Buy, Sell"],
    ["amount", "Yes", "BTC (up to 8 decimals), or USD for Bank/Exchange USD rows. Transfer: what left the account, fee included. Withdrawal: what the recipient got, fee on top"],
    ["from_account", "Yes", "Source account name"],
    ["to_account", "Yes", "Destination account name"],
    ["cost_basis_usd", "Conditional", "Buy: USD paid for the BTC, before the fee (the fee column is added to the basis). BTC Deposit: required (0 if unknown); Income/Interest/Reward blank = that day's value"],
    ["proceeds_usd", "Conditional", "Sell: gross USD, before the fee (the fee is subtracted). Spent withdrawal: value received; blank = that day's value"],
    ["fee_amount", "No", "Fee amount (never also included in cost_basis_usd or proceeds_usd)"],
    ["fee_currency", "No", "USD for Buy/Sell and moves out of Bank/Exchange USD; BTC for moves out of Wallet/Exchange BTC"],
    ["source", "No", "For Deposits: N/A, MyBTC, Gift, Income, Interest, Reward"],
    ["purpose", "Conditional", "For Withdrawals: Spent, Gift, Donation, Lost"],
    ["notes", "No", "Optional notes (not imported, for your reference only)"],
    ["fee_usd", "No", "Transfer/Withdrawal with a BTC fee: what the fee was worth in USD. Blank = fee x that day's BTC price"],
    ["fmv_usd", "No", "Gift, Donation or Lost withdrawal: its fair market value that day (shown in the tax report)"],
    ["broker_reporting", "No", "Sell/Withdrawal: only when your broker's 1099-DA/1099-B differs: none, proceeds or basis. Blank = automatic"],
    ["fee_usd_typed", "No", "With fee_usd: yes (or blank) if you typed that value, no if it was that day's price (the export writes it)"],
]

TYPES = [
    ["Type", "Description"],
    ["Deposit", "BTC entering your portfolio (purchase, gift received, income, etc.)"],
    ["Withdrawal", "BTC leaving your portfolio (spent, gift sent, donation, loss)"],
    ["Transfer", "Moving BTC between your own wallets (no taxable event)"],
    ["Buy", "Purchasing BTC on an exchange with USD"],
    ["Sell", "Selling BTC on an exchange for USD"],
]

ACCOUNTS = [
    ["Account", "Description"],
    ["Bank", "Your fiat bank account (USD)"],
    ["Wallet", "Your self-custody Bitcoin wallet"],
    ["Exchange USD", "USD balance on an exchange"],
    ["Exchange BTC", "BTC balance on an exchange"],
    ["External", "Outside your portfolio (source for deposits, destination for withdrawals)"],
]

SOURCES = [
    ["Value", "Description"],
    ["N/A", "Not applicable or unspecified"],
    ["MyBTC", "BTC you already owned (transferring in)"],
    ["Gift", "Received as a gift"],
    ["Income", "Payment for goods/services"],
    ["Interest", "Earned as interest"],
    ["Reward", "Mining, staking, or other rewards"],
]

PURPOSES = [
    ["Value", "Description"],
    ["Spent", "Used to purchase goods/services (taxable sale)"],
    ["Gift", "Given as a gift"],
    ["Donation", "Donated to charity"],
    ["Lost", "Lost or stolen BTC"],
]

ACCOUNT_RULES = [
    ["Type", "From Account", "To Account", "Required Fields"],
    ["Deposit", "External", "Wallet or\nExchange BTC", "cost_basis_usd required (0 if unknown);\nIncome/Interest/Reward: blank = that day's value"],
    ["Withdrawal", "Wallet or\nExchange BTC", "External", "purpose required;\nproceeds_usd for \"Spent\""],
    ["Transfer", "Any account", "Another account,\nsame currency", "Fee in the sending account's currency;\naccounts must be different"],
    ["Buy", "Bank or\nExchange USD", "Exchange BTC", "cost_basis_usd required;\nfee must be USD"],
    ["Sell", "Exchange BTC", "Exchange USD", "proceeds_usd required;\nfee must be USD"],
]

DATE_FORMATS = [
    ["Format", "Example"],
    ["ISO8601 with Z (preferred)", "2024-01-15T10:30:00Z"],
    ["ISO8601 with timezone", "2024-01-15T10:30:00+00:00"],
    ["ISO8601 without timezone", "2024-01-15T10:30:00"],
    ["Date with time", "2024-01-15 10:30:00"],
    ["Date only", "2024-01-15"],
    ["US format with time", "01/15/2024 10:30:00"],
    ["US format date only", "01/15/2024"],
]

EXAMPLES = [
    ("Buy from Exchange USD:", "2024-01-15T10:30:00Z,Buy,0.012,Exchange USD,Exchange BTC,500.00,,5.00,USD,,,"),
    ("Buy from Bank (auto-buy):", "2024-01-20T08:00:00Z,Buy,0.05,Bank,Exchange BTC,2500.00,,10.00,USD,,,"),
    ("Sell (selling BTC on exchange):", "2024-02-15T11:30:00Z,Sell,0.3,Exchange BTC,Exchange USD,,15000.00,10.00,USD,,,"),
    ("Deposit (BTC entering your wallet):", "2024-01-20T14:00:00Z,Deposit,0.5,External,Wallet,21000.00,,,Income,,"),
    ("Withdrawal (spending BTC):", "2024-03-01T09:00:00Z,Withdrawal,0.1,Wallet,External,,5500.00,,,Spent,"),
    ("Transfer (moving between wallets):", "2024-02-01T16:45:00Z,Transfer,1.0,Exchange BTC,Wallet,,,0.0001,BTC,,,"),
]

COMMON_ERRORS = [
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

TABLE_STYLE = TableStyle([
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


def generate_csv_instructions_pdf() -> Path:
    """Write the guide next to the app's other assets; returns its path."""
    output_path = Path(__file__).parent.parent / "assets" / "csv_import_instructions.pdf"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    guide = _Guide()
    story = [
        *guide.overview(),
        *guide.quick_start(),
        PageBreak(),
        *guide.field_reference(),
        PageBreak(),
        *guide.account_rules(),
        *guide.date_formats(),
        PageBreak(),
        *guide.examples(),
        *guide.troubleshooting(),
    ]
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    doc.build(story)
    print(f"PDF generated: {output_path}")
    return output_path


class _Guide:
    """The guide's paragraph styles, and its sections as lists of flowables."""

    def __init__(self):
        sample = getSampleStyleSheet()
        self.title = ParagraphStyle(name="Title", parent=sample["Title"], fontSize=24, spaceAfter=20)
        self.heading1 = ParagraphStyle(
            name="Heading1Custom", parent=sample["Heading1"], fontSize=16, spaceBefore=20, spaceAfter=10,
            textColor=colors.HexColor("#333333"),
        )
        self.heading2 = ParagraphStyle(
            name="Heading2Custom", parent=sample["Heading2"], fontSize=13, spaceBefore=15, spaceAfter=8,
            textColor=colors.HexColor("#444444"),
        )
        self.normal = ParagraphStyle(name="NormalCustom", parent=sample["Normal"], fontSize=10, leading=14, spaceAfter=8)
        self.bullet = ParagraphStyle(name="Bullet", parent=self.normal, leftIndent=20, bulletIndent=10, spaceAfter=4)
        self.code = ParagraphStyle(
            name="Code", parent=self.normal, fontName="Courier", fontSize=9, leftIndent=20,
            backColor=colors.HexColor("#f5f5f5"), borderPadding=5,
        )
        self.warning = ParagraphStyle(
            name="Warning", parent=self.normal, backColor=colors.HexColor("#fff3cd"), borderPadding=10,
            borderColor=colors.HexColor("#ffc107"), borderWidth=1, spaceBefore=10, spaceAfter=10,
        )
        self.cell = ParagraphStyle("Cell", parent=sample["Normal"], fontSize=8.5, leading=10.5)

    def table(self, rows: list, widths: list, wrap: bool = False) -> Table:
        """A guide table; `wrap` makes the body cells Paragraphs, so long text
        wraps inside its column."""
        if wrap:
            rows = [rows[0]] + [[Paragraph(str(c).replace("\n", "<br/>"), self.cell) for c in row] for row in rows[1:]]
        table = Table(rows, colWidths=[width * inch for width in widths])
        table.setStyle(TABLE_STYLE)
        return table

    def overview(self) -> list:
        return [
            Paragraph("BitcoinTX CSV Import Guide", self.title),
            Spacer(1, 10),
            Paragraph("Overview", self.heading1),
            Paragraph(
                "The CSV Import feature allows you to bulk-import your Bitcoin transaction history "
                "into BitcoinTX. This is useful for:",
                self.normal
            ),
            Paragraph("• Setting up a new installation with existing data", self.bullet),
            Paragraph("• Migrating from another tracking system", self.bullet),
            Paragraph("• Restoring from a CSV backup", self.bullet),
            Paragraph(
                "<b>Important:</b> The database must be empty before importing. "
                "This ensures clean FIFO cost basis calculations. If you have existing "
                "transactions, delete them first from the Settings page.",
                self.warning
            ),
        ]

    def quick_start(self) -> list:
        steps = [
            ("Step 1: Download the Template",
             "Go to Settings → Data Management and click \"Download Template\". "
             "This gives you a CSV file with the correct column headers and sample rows."),
            ("Step 2: Fill in Your Data",
             "Open the template in a spreadsheet application (Excel, Google Sheets, etc.) "
             "and replace the sample rows with your actual transaction data. "
             "Delete any sample rows you don't need."),
            ("Step 3: Preview the Import",
             "Upload your CSV file and click \"Preview\". The system validates all rows and "
             "shows you any errors or warnings. Fix any issues before proceeding."),
            ("Step 4: Execute the Import",
             "If the preview shows no errors, click \"Import\" to create all transactions. "
             "The import is atomic – if anything fails, no transactions are created."),
        ]
        story = [Paragraph("Quick Start Guide", self.heading1)]
        for title, text in steps:
            story += [Paragraph(title, self.heading2), Paragraph(text, self.normal)]
        return story

    def field_reference(self) -> list:
        return [
            Paragraph("Field Reference", self.heading1),
            Paragraph("CSV Columns", self.heading2),
            self.table(COLUMNS, [1.3, 0.9, 4.5], wrap=True),
            Paragraph(
                "Settings > Export CSV writes these same columns, so an export imports back to the same ledger.",
                self.normal
            ),
            Paragraph("Transaction Types", self.heading2),
            self.table(TYPES, [1.3, 5.4]),
            Paragraph("Account Names", self.heading2),
            self.table(ACCOUNTS, [1.5, 5.2]),
            Paragraph("Source Values (for Deposits)", self.heading2),
            self.table(SOURCES, [1.3, 5.4]),
            Paragraph("Purpose Values (for Withdrawals)", self.heading2),
            self.table(PURPOSES, [1.3, 5.4]),
        ]

    def account_rules(self) -> list:
        return [
            Paragraph("Account Rules by Transaction Type", self.heading1),
            Paragraph(
                "Each transaction type has specific account requirements. "
                "The system enforces these rules during validation.",
                self.normal
            ),
            self.table(ACCOUNT_RULES, [1.0, 1.3, 1.3, 3.1], wrap=True),
        ]

    def date_formats(self) -> list:
        return [
            Paragraph("Supported Date Formats", self.heading1),
            Paragraph(
                "The following date formats are accepted. ISO8601 with timezone is recommended. "
                "A date or time without a timezone is read in your tax timezone (Settings), and a "
                "date alone means noon that day, so it stays in the right tax year:",
                self.normal
            ),
            self.table(DATE_FORMATS, [2.5, 2.5]),
        ]

    def examples(self) -> list:
        story = [
            Paragraph("Example Rows", self.heading1),
            Paragraph(
                "Below are example CSV rows for each transaction type. "
                "Use these as templates for your own data.",
                self.normal
            ),
        ]
        for title, row in EXAMPLES:
            story += [Paragraph(title, self.heading2), Paragraph(row, self.code)]
        return story

    def troubleshooting(self) -> list:
        footer = ParagraphStyle(name="Footer", parent=self.normal, alignment=1, textColor=colors.gray)
        return [
            Paragraph("Troubleshooting", self.heading1),
            Paragraph("Common Errors", self.heading2),
            self.table(COMMON_ERRORS, [2.8, 3.9]),
            Spacer(1, 20),
            Paragraph(
                "<b>Tip:</b> Use the Preview feature to validate your CSV before importing. "
                "Fix all errors shown in red before clicking Import.",
                self.warning
            ),
            Spacer(1, 30),
            Paragraph("Generated by BitcoinTX • For more help, visit the project repository", footer),
        ]


if __name__ == "__main__":
    generate_csv_instructions_pdf()
