"""
The complete tax report per account (2.0 spec 5.7; card B4 #349): each
capital-gains row says the account it left, each lot held when the year
began its account, and "Sales by exchange" gives each exchange's Sells of
the year (its 1099-DA switch, their boxes and totals, network fees left
out), to set beside the Form 1099-DA it sends. Informational: every figure
stays as it is, so its totals are its Sells' rows. In the PDF the account
is the Kind cell's second line, and a 40-character name wraps inside it.
"""

import io

from pypdf import PdfReader
from reportlab.platypus import Table

from backend.services.reports.complete_tax_report import _TaxReport, generate_comprehensive_tax_report
from backend.tests import two_exchanges
from backend.tests.two_exchanges import (
    BANK, EXCHANGE_BTC, EXCHANGE_USD, EXTERNAL, KRAKEN_BTC, KRAKEN_USD, OVERSEAS_BTC, OVERSEAS_USD, WALLET,
)

ledger = two_exchanges.ledger  # the fixture: a fresh ledger with Kraken and Overseas

# A cell's padding, left and right (pdf_layout.data_table)
PADDING = 10


def shown(report: dict) -> str:
    """The PDF's text, all whitespace removed (cells wrap)."""
    pdf = generate_comprehensive_tax_report(report)
    return "".join("".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).split())


def a_year_on_three_exchanges(ledger) -> dict:
    """2026: Sells on the first exchange (G), Kraken (H and G) and Overseas, whose switch is off (I); a
    network fee leaving Kraken, and a spend from the wallet."""
    ledger.switch("Overseas", False)
    ledger.save("Buy", "2025-06-10", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="40000.00")
    ledger.save("Buy", "2026-01-05", BANK, EXCHANGE_BTC, "1.00000000", cost_basis_usd="90000.00")
    ledger.save("Buy", "2026-02-01", BANK, KRAKEN_BTC, "1.00000000", cost_basis_usd="80000.00")
    ledger.save("Buy", "2026-02-01", BANK, OVERSEAS_BTC, "1.00000000", cost_basis_usd="70000.00")
    ledger.save("Transfer", "2026-02-15", EXCHANGE_BTC, WALLET, "0.50000000", fee_amount="0.00010000", fee_usd="9.00")
    ledger.save("Sell", "2026-03-01", KRAKEN_BTC, KRAKEN_USD, "1.50000000", gross_proceeds_usd="135000.00")
    ledger.save("Sell", "2026-04-01", OVERSEAS_BTC, OVERSEAS_USD, "0.50000000", gross_proceeds_usd="41000.00")
    ledger.save("Transfer", "2026-05-01", KRAKEN_BTC, WALLET, "0.20000000", fee_amount="0.00010000", fee_usd="8.00")
    ledger.save("Withdrawal", "2026-05-15", WALLET, EXTERNAL, "0.10000000", purpose="Spent",
                proceeds_usd="9500.00")
    ledger.save("Sell", "2026-06-01", EXCHANGE_BTC, EXCHANGE_USD, "0.30000000", gross_proceeds_usd="27000.00")
    return ledger.report(2026)


def test_each_row_says_the_account_it_left(ledger):
    report = a_year_on_three_exchanges(ledger)
    assert [(r["kind"], r["box"], r["account"]) for r in report["capital_gains_transactions"]] == [
        ("Network fee", "I", "Exchange BTC"),
        ("Sale", "H", "Kraken BTC"), ("Sale", "G", "Kraken BTC"),
        ("Sale", "I", "Overseas BTC"),
        ("Network fee", "I", "Kraken BTC"),
        ("Spend", "I", "Wallet"),
        ("Sale", "G", "Exchange BTC"),
    ]


def test_each_lot_held_when_the_year_began_says_its_account(ledger):
    a_year_on_three_exchanges(ledger)
    report = ledger.report(2027)
    assert sorted((lot["account"], lot["quantity"]) for lot in report["start_of_year_balances"]) == [
        ("Exchange BTC", 0.2), ("Kraken BTC", 0.3), ("Overseas BTC", 0.5), ("Wallet", 0.1999), ("Wallet", 0.3999)]


def test_sales_by_exchange_add_up_to_their_sells_rows_with_network_fees_left_out(ledger):
    report = a_year_on_three_exchanges(ledger)
    sales = report["sales_by_exchange"]
    assert [(s["exchange"], s["sends_1099da"], s["boxes"], s["rows"]) for s in sales] == [
        ("Exchange", True, ["G"], 1), ("Kraken", True, ["G", "H"], 2), ("Overseas", False, ["I"], 1)]
    for s in sales:
        rows = [r for r in report["capital_gains_transactions"]
                if r["kind"] == "Sale" and r["account"] == f"{s['exchange']} BTC"]
        assert len(rows) == s["rows"]
        for total, column in (("proceeds", "proceeds"), ("cost", "cost"), ("gain_loss", "gain_loss")):
            assert round(s[total], 2) == round(sum(r[column] for r in rows), 2), (s["exchange"], total)
    assert (sales[1]["proceeds"], sales[1]["cost"], sales[1]["gain_loss"]) == (135000.0, 80000.0, 55000.0)


def test_a_1x_ledger_shows_one_exchange(ledger):
    ledger.save("Buy", "2025-01-10", BANK, EXCHANGE_BTC, "1.00000000", cost_basis_usd="40000.00")
    ledger.save("Sell", "2025-03-01", EXCHANGE_BTC, EXCHANGE_USD, "0.25000000", gross_proceeds_usd="22000.00")
    report = ledger.report(2025)
    assert report["sales_by_exchange"] == [{"exchange": "Exchange", "sends_1099da": True, "boxes": ["H"], "rows": 1,
                                            "proceeds": 22000.0, "cost": 10000.0, "gain_loss": 12000.0}]
    text = shown(report)
    assert "Salesbyexchange" in text and "SaleExchangeBTC" in text


def test_before_2025_no_exchange_sent_a_1099da(ledger):
    ledger.save("Buy", "2024-01-10", BANK, EXCHANGE_BTC, "1.00000000", cost_basis_usd="40000.00")
    ledger.save("Sell", "2024-03-01", EXCHANGE_BTC, EXCHANGE_USD, "0.25000000", gross_proceeds_usd="12000.00")
    text = shown(ledger.report(2024))
    assert "Exchange—C1$12,000.00" in text[text.index("Salesbyexchange"):]


def test_a_year_without_a_sell_has_no_sales_by_exchange(ledger):
    ledger.save("Buy", "2025-01-10", BANK, EXCHANGE_BTC, "1.00000000", cost_basis_usd="40000.00")
    ledger.save("Transfer", "2025-02-01", EXCHANGE_BTC, WALLET, "0.50000000", fee_amount="0.00010000", fee_usd="9.00")
    report = ledger.report(2025)
    assert report["sales_by_exchange"] == []
    assert "Salesbyexchange" not in shown(report)


def test_the_pdf_names_each_rows_account_and_each_exchange(ledger):
    text = shown(a_year_on_three_exchanges(ledger))
    for kind_cell in ("SaleKrakenBTC", "SaleOverseasBTC", "NetworkfeeKrakenBTC", "SpendWallet"):
        assert kind_cell in text
    after = text[text.index("Salesbyexchange"):]
    assert all(name in after for name in ("Exchange", "Kraken", "Overseas"))


def test_a_40_character_name_wraps_inside_the_kind_cell(ledger):
    long_wallet = "X" * 40  # one word: wrapped anywhere (the cells' wordWrap)
    r = ledger.client.post("/api/accounts/", json={"kind": "wallet", "name": long_wallet})
    assert r.status_code == 201, r.text
    wallet = r.json()[0]["id"]
    long_exchange = "Pacific Northwest Digital Asset Bank"  # 36 characters: its BTC account has 40
    r = ledger.client.post("/api/accounts/", json={"kind": "exchange", "name": long_exchange})
    assert r.status_code == 201, r.text
    usd, btc = (a["id"] for a in r.json())
    ledger.save("Buy", "2025-01-10", BANK, btc, "1.00000000", cost_basis_usd="40000.00")
    ledger.save("Transfer", "2025-02-01", btc, wallet, "0.50000000")
    ledger.save("Withdrawal", "2025-03-01", wallet, EXTERNAL, "0.10000000", purpose="Spent", proceeds_usd="9000.00")
    ledger.save("Sell", "2025-04-01", btc, usd, "0.20000000", gross_proceeds_usd="18000.00")
    report = ledger.report(2025)
    names = [f"{long_exchange} BTC", long_wallet]
    assert [r["account"] for r in report["capital_gains_transactions"]] == [long_wallet, names[0]]
    tax_report = _TaxReport(report)
    table = next(f for f in tax_report.capital_gains_detail() if isinstance(f, Table))
    kind_width = table._colWidths[2] - PADDING  # the Kind column, as the report lays it out
    for row in report["capital_gains_transactions"]:
        kind, account = tax_report.disposal_row(row)[2]
        account.wrap(kind_width, 1000)
        assert len(account.blPara.lines) > 1, row["account"]
        # Each line's room to spare (a line of words keeps it first, one of characters as extraSpace)
        room = [line.extraSpace if hasattr(line, "extraSpace") else line[0] for line in account.blPara.lines]
        assert min(room) >= 0, row["account"]  # none runs over the next column
    text = shown(report)
    assert all("".join(name.split()) in text for name in names)
