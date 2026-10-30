"""
The tables of docs/HAND-TEST.md (#844), never typed: the figures come from
testdata/reference_figures.json and the files' rows and warnings from the
app's own previews, so the guide can't say what the app no longer does.
test_hand_test_guide_844.py fails when one is stale; `make test-pack` rewrites
them. Each sits between `<!-- begin NAME -->` and `<!-- end NAME -->`.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from backend.services.reports.complete_tax_report import fmt_btc, fmt_gain, fmt_usd

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "HAND-TEST.md"
FILES_FOLDER = ROOT / "testdata" / "exchange_files"
# A new install's accounts and their lines on the Dashboard's Portfolio Overview
DASHBOARD_LINES = (("Bank", "Bank (USD)"), ("Exchange USD", "Exchange (USD)"), ("Exchange BTC", "Exchange (BTC)"),
                   ("Wallet", "Wallet (BTC)"))
BTC_NAMES = ("Exchange BTC", "Wallet")
KIND_WORDS = {"wallet": "Add a wallet", "exchange": "Add an exchange", "bank": "Add a bank"}


# What a row sends at the screen's Import (RiverPreview's rows)
SENT = ("row_number", "date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd",
        "fee_amount", "fee_currency", "source", "purpose", "price_moment")


def rows_to_send(preview: dict, untick: tuple[int, ...] = ()) -> list[dict]:
    """A preview's rows as the screen's Import sends them, a value from the price marked so."""
    return [{key: p.get(key) for key in SENT} | {"cost_basis_typed": "no" if p["basis_autofilled"] else None}
            for p in preview["proposals"] if p["row_number"] not in untick]


@dataclass(frozen=True)
class ExchangeFile:
    """A sample file and the choice to make for it in "Exchange file": the
    rows to untick, and the file it follows without a Delete All between
    (its coins come from that one)."""
    name: str
    mapping_id: str
    choice: str
    what: str
    untick: tuple[int, ...] = ()
    after: str | None = None


# Every file of testdata/exchange_files/, by exchange (the guide's test fails on one left out)
EXCHANGE_FILES = (
    ExchangeFile("river_bitcoin_activity.csv", "river", "River", "Bitcoin activity: each kind of row River's file has"),
    ExchangeFile("coinbase_2021.csv", "coinbase", "Coinbase", "the oldest statement"),
    ExchangeFile("coinbase_2022.csv", "coinbase", "Coinbase", "a statement from before 2024"),
    ExchangeFile("coinbase_2024.csv", "coinbase", "Coinbase", "a statement with an ID column first"),
    ExchangeFile("coinbase_2026.csv", "coinbase", "Coinbase", "today's statement, of 13 columns"),
    ExchangeFile("coinbase_advance_trade.csv", "coinbase", "Coinbase", "Advanced Trade's rows"),
    ExchangeFile("kraken_ledgers.csv", "kraken", "Kraken", "a ledger of each kind of row"),
    ExchangeFile("kraken_fee_credits.csv", "kraken", "Kraken", "trades paid with fee credits"),
    ExchangeFile("strike_activity.csv", "strike", "Strike", "the Activity report"),
    ExchangeFile("strike_statement.csv", "strike", "Strike", "a statement"),
    ExchangeFile("swan_deposits_and_purchases.csv", "swan", "Swan: deposits and purchases", "deposits and purchases",
                 untick=(9,)),
    ExchangeFile("swan_withdrawals.csv", "swan-withdrawals", "Swan: withdrawals", "withdrawals",
                 after="swan_deposits_and_purchases.csv"),
    ExchangeFile("cash_app_bitcoin.csv", "cash-app", "Cash App", "the Bitcoin file"),
    ExchangeFile("cash_app_activity.csv", "cash-app", "Cash App", "the activity file"),
)


def replace_sections(text: str, sections: dict[str, str]) -> str:
    """The guide with each section's lines put in between its marks."""
    for name, body in sections.items():
        begin, end = f"<!-- begin {name} -->", f"<!-- end {name} -->"
        pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.S)
        if not pattern.search(text):
            raise ValueError(f"the guide has no {begin}")
        text = pattern.sub(lambda _: f"{begin}\n{body.strip()}\n{end}", text)
    return text


def sections_in(text: str) -> dict[str, str]:
    """The guide's sections as they are now: name -> lines."""
    return {name: body.strip() for name, body in
            re.findall(r"<!-- begin (\S+) -->\n(.*?)<!-- end \1 -->", text, re.S)}


def table(header: tuple[str, ...], rows: list[tuple]) -> str:
    """A Markdown table, its numbers lined up on the right as the report's are."""
    def line(cells) -> str:
        return "| " + " | ".join(str(cell) for cell in cells) + " |"
    return "\n".join([line(header), line(tuple("---" if i == 0 else "---:" for i in range(len(header)))),
                      *map(line, rows)])


def accounts_table(listed: list[dict]) -> str:
    """The accounts to add, in the ledger's order: an exchange once, under
    the name its accounts have now, which is what the CSV names."""
    rows, seen = [], set()
    for account in listed:
        name = account["name"].removesuffix(f" {account['currency']}") if account["kind"] == "exchange" else account["name"]
        if name in seen:
            continue
        seen.add(name)
        answer = ("Yes" if account.get("sends_1099da", True) else "No") if account["kind"] == "exchange" else "not asked"
        rows.append((KIND_WORDS[account["kind"]], name, answer))
    return table(("Button", "Name to type", "Does this exchange send you a Form 1099-DA?"), rows)


def figures_tables(figures: dict) -> str:
    """Each year's figures, as the Complete Tax Report prints them."""
    return "\n\n".join(_year_tables(year, figures["years"][year]["report"]) for year in sorted(figures["years"]))


def _year_tables(year: str, report: dict) -> str:
    boxes = table(("Box", "Schedule D line", "Rows", "Proceeds", "Cost basis", "Gain (loss)"),
                  [(b["box"], b["line"], b["rows"], fmt_usd(b["proceeds"]), fmt_usd(b["cost"]), fmt_gain(b["gain_loss"]))
                   for b in report["form_8949_boxes"]])
    income = report["income_summary"]
    rebates = report["rebates"]
    return "\n\n".join([
        f"### {year}",
        boxes,
        ("**Income:** " + ", ".join(f"{kind} {fmt_usd(income.get(kind, 0))}" for kind in ("Income", "Interest", "Reward"))
         + f"; total {fmt_usd(income.get('Total', 0))}."),
        (f"**Rebates (not income):** {fmt_btc(sum(r['amount'] for r in rebates))} BTC, "
         f"{fmt_usd(sum(r['value_usd'] for r in rebates))}."),
        f"**Holdings at December 31, {year}:**",
        _holdings_table(report["end_of_year_balances"]),
    ])


def _holdings_table(balances: list[dict]) -> str:
    accounts: dict[str, dict] = defaultdict(lambda: {"lots": 0, "btc": 0.0, "cost": 0.0})
    total = next(b for b in balances if b["asset"] == "Total")
    for lot in balances:
        if lot["asset"] != "Total":
            account = accounts[lot["account"]]
            account["lots"] += 1
            account["btc"] += lot["quantity"]
            account["cost"] += lot["cost"]
    rows = [(name, a["lots"], fmt_btc(a["btc"]), fmt_usd(a["cost"])) for name, a in sorted(accounts.items())]
    rows.append(("**Total**", f"**{sum(a['lots'] for a in accounts.values())}**", f"**{fmt_btc(total['quantity'])}**",
                 f"**{fmt_usd(total['cost'])}**"))
    return table(("Account", "Lots", "BTC", "Cost basis"), rows)


def problem_text(problem: dict) -> str:
    """A warning as the preview's list shows it (frontend/src/utils/importProblem.ts)."""
    number, message = problem["row_number"], problem["message"]
    return message if number <= 0 else f"Row {number}: {message}"


def balances_line(balances: list[dict]) -> str:
    """Portfolio Overview's lines on an install with one of each account,
    in its order (frontend/src/utils/dashboard.ts), those holding something."""
    held = {b["name"]: Decimal(str(b["balance"])) for b in balances}
    said = []
    for name, label in DASHBOARD_LINES:
        amount = held.get(name, Decimal(0))
        if amount:
            said.append(f"{label} {fmt_btc(float(amount))} BTC" if name in BTC_NAMES else f"{label} {_dollars(amount)}")
    return ", ".join(said)


def _dollars(amount: Decimal) -> str:
    return f"\u2212{fmt_usd(float(-amount))}" if amount < 0 else fmt_usd(float(amount))  # a real minus, as on screen


def file_section(file: ExchangeFile, preview: dict, balances: list[dict]) -> str:
    """One sample file: its link, the choice, what the preview shows, and what the accounts hold afterwards."""
    said = [f"#### [{file.name}](../testdata/exchange_files/{file.name}) ({file.what})", ""]
    if file.after:
        said.append(f"- **First:** import {file.after} as above, and don't delete it: this file sends its coins.")
    said += [f"- **Exchange file:** {file.choice}.",
             f"- **The preview:** {preview['total_rows']} rows in the file, button \"Import {preview['new_count']} "
             f"Transaction(s)\", no errors, {len(preview['warnings'])} warnings" + (":" if preview["warnings"] else ".")]
    said += [f"  - {problem_text(w)}" for w in preview["warnings"]]
    for row in file.untick:
        proposal = next(p for p in preview["proposals"] if p["row_number"] == row)
        said.append(f"- **Untick the {proposal['type']} from {proposal['from_account']} of {proposal['amount']} BTC** "
                    f"(its Import box). The button then says \"Import {preview['new_count'] - len(file.untick)} "
                    "Transaction(s)\". Its coins come from a wallet that holds none here: left ticked, the import "
                    "stops at \"Not enough BTC\" and saves nothing, as it should.")
    said.append(f"- **Afterwards:** {balances_line(balances)}.")
    return "\n".join(said)


def template_section(preview: dict, balances: list[dict]) -> str:
    said = [csv_preview_line(preview["valid_rows"], preview["total_rows"], len(preview["warnings"]))]
    said += [f"  - {problem_text(w)}" for w in preview["warnings"]]
    said.append(f"- **The button:** \"Import {preview['valid_rows']} Transactions\".")
    said.append(f"- **Afterwards:** {balances_line(balances)}.")
    return "\n".join(said)


def csv_preview_line(valid: int, total: int, warnings: int) -> str:
    """What CsvImportPreview's header says, no errors or warnings being no mention of them."""
    said = f"- **The preview:** \"{valid} valid / {total} total rows\", with no errors"
    return said + (f" and {warnings} warnings:" if warnings else " and no warnings.")
