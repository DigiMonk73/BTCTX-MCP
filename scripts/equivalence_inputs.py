"""
The inputs scripts/equivalence_check.py feeds BitcoinTX: extra entries for
the MCP tools and the entry import, and bad inputs (one per validation
rule, as far as a rule shows from outside) so every error message is in the
snapshot. The ledgers themselves come from the tests (golden, seed, random).
"""

BANK, WALLET, EXCH_USD, EXCH_BTC, EXTERNAL = 1, 2, 3, 4, 99

# Valid API payloads after the golden ledger's last transaction; the base for
# the invalid ones.
API_PAYLOADS = {
    "buy": dict(type="Buy", timestamp="2025-07-01T15:00:00Z", from_account_id=BANK, to_account_id=EXCH_BTC,
                amount="0.01", cost_basis_usd="1000", fee_amount="1", fee_currency="USD"),
    "sell": dict(type="Sell", timestamp="2025-07-02T15:00:00Z", from_account_id=EXCH_BTC,
                 to_account_id=EXCH_USD, amount="0.01", gross_proceeds_usd="1200", fee_amount="1",
                 fee_currency="USD"),
    "deposit_income": dict(type="Deposit", timestamp="2025-07-03T15:00:00Z", from_account_id=EXTERNAL,
                           to_account_id=WALLET, amount="0.001", fee_amount="0", fee_currency="BTC",
                           source="Income"),
    "deposit_gift": dict(type="Deposit", timestamp="2025-07-04T15:00:00Z", from_account_id=EXTERNAL,
                         to_account_id=WALLET, amount="0.001", cost_basis_usd="50", fee_amount="0",
                         fee_currency="BTC", source="Gift"),
    "deposit_usd": dict(type="Deposit", timestamp="2025-07-05T15:00:00Z", from_account_id=EXTERNAL,
                        to_account_id=BANK, amount="500", fee_amount="0", fee_currency="USD", source="N/A"),
    "withdrawal_spent": dict(type="Withdrawal", timestamp="2025-07-06T15:00:00Z", from_account_id=WALLET,
                             to_account_id=EXTERNAL, amount="0.001", proceeds_usd="60", fee_amount="0.00001",
                             fee_currency="BTC", purpose="Spent"),
    "withdrawal_gift": dict(type="Withdrawal", timestamp="2025-07-07T15:00:00Z", from_account_id=WALLET,
                            to_account_id=EXTERNAL, amount="0.001", fmv_usd="70", fee_amount="0",
                            fee_currency="BTC", purpose="Gift"),
    "withdrawal_usd": dict(type="Withdrawal", timestamp="2025-07-08T15:00:00Z", from_account_id=BANK,
                           to_account_id=EXTERNAL, amount="100", fee_amount="0", fee_currency="USD"),
    "transfer": dict(type="Transfer", timestamp="2025-07-09T15:00:00Z", from_account_id=EXCH_BTC,
                     to_account_id=WALLET, amount="0.01", fee_amount="0.0001", fee_currency="BTC"),
    "transfer_usd": dict(type="Transfer", timestamp="2025-07-10T15:00:00Z", from_account_id=BANK,
                         to_account_id=EXCH_USD, amount="100", fee_amount="0", fee_currency="USD"),
}

ACCOUNT_IDS = (BANK, WALLET, EXCH_USD, EXCH_BTC, 5, 6, EXTERNAL, 7)

# (field, value) changes applied to each payload, for create (POST) and edit
# (PUT). None removes the field.
API_CHANGES = (
    [("amount", v) for v in ("0", "-1", "abc", "1.123456789", None, "1000000")]
    + [("timestamp", v) for v in ("2099-01-01T00:00:00Z", "yesterday", None, "2025-07-01")]
    + [("from_account_id", v) for v in ACCOUNT_IDS]
    + [("to_account_id", v) for v in ACCOUNT_IDS]
    + [("type", v) for v in ("Buy", "Sell", "Deposit", "Withdrawal", "Transfer", "Swap")]
    + [("fee_amount", v) for v in ("-1", "abc", "0.5", None)]
    + [("fee_currency", v) for v in ("EUR", "BTC", "USD", None)]
    + [("cost_basis_usd", v) for v in ("-1", "0", "abc", "100", None)]
    + [("proceeds_usd", v) for v in ("-1", "100")]
    + [("gross_proceeds_usd", v) for v in ("-1", "100")]
    + [("source", v) for v in ("Income", "Gift", "MyBTC", "Interest", "Reward", "N/A", "Stolen", None)]
    + [("purpose", v) for v in ("Spent", "Gift", "Donation", "Lost", "Stolen", None)]
    + [("broker_reporting", v) for v in ("none", "proceeds", "basis", "automatic", "weird")]
    + [("fmv_usd", v) for v in ("-1", "50")]
    + [("fee_usd", v) for v in ("-1", "5")]
    + [("is_locked", True)]
)

CSV_COLUMNS = (
    "date", "type", "amount", "from_account", "to_account", "cost_basis_usd", "proceeds_usd",
    "fee_amount", "fee_currency", "source", "purpose", "notes", "fee_usd", "fmv_usd",
    "broker_reporting", "fee_usd_typed",
)

# CSV rows that import on an empty ledger, in order.
CSV_BASE_ROWS = {
    "deposit_usd": {"date": "2024-01-01T10:00:00Z", "type": "Deposit", "amount": "20000",
                    "from_account": "External", "to_account": "Bank"},
    "buy": {"date": "2024-01-02T10:00:00Z", "type": "Buy", "amount": "0.1", "from_account": "Bank",
            "to_account": "Exchange BTC", "cost_basis_usd": "4000", "fee_amount": "10", "fee_currency": "USD"},
    "deposit_income": {"date": "2024-01-03T10:00:00Z", "type": "Deposit", "amount": "0.01",
                       "from_account": "External", "to_account": "Wallet", "source": "Income"},
    "transfer": {"date": "2024-01-04T10:00:00Z", "type": "Transfer", "amount": "0.05",
                 "from_account": "Exchange BTC", "to_account": "Wallet", "fee_amount": "0.0001",
                 "fee_currency": "BTC", "fee_usd": "4.20", "fee_usd_typed": "yes"},
    "sell": {"date": "2024-01-05T10:00:00Z", "type": "Sell", "amount": "0.02", "from_account": "Exchange BTC",
             "to_account": "Exchange USD", "proceeds_usd": "900", "fee_amount": "2", "fee_currency": "USD",
             "broker_reporting": "basis"},
    "withdrawal_gift": {"date": "2024-01-06T10:00:00Z", "type": "Withdrawal", "amount": "0.01",
                        "from_account": "Wallet", "to_account": "External", "purpose": "Gift", "fmv_usd": "450"},
    "withdrawal_spent": {"date": "2024-01-07T10:00:00Z", "type": "Withdrawal", "amount": "0.01",
                         "from_account": "Wallet", "to_account": "External", "purpose": "Spent",
                         "proceeds_usd": "450", "fee_amount": "0.00001", "fee_currency": "BTC"},
}

_NUMBERS = ("", "abc", "-1", "0", "1.123456789", "1,000", "1e3")
_ACCOUNTS = ("", "bank", "WALLET", "Exchange USD", "exchange btc", "External", "Nowhere")

# Values tried in each column of each base row.
CSV_CHANGES = {
    "date": ("", "abc", "2099-01-01T00:00:00Z", "2024-13-45", "01/15/2024", "2024-01-15",
             "2024-01-15T10:00:00", "2024-01-15 10:00:00", "2024-01-15T10:00:00+09:00"),
    "type": ("", "buy", "SELL", "Swap", "Deposit", "Withdrawal", "Transfer"),
    "amount": _NUMBERS,
    "from_account": _ACCOUNTS,
    "to_account": _ACCOUNTS,
    "cost_basis_usd": _NUMBERS,
    "proceeds_usd": _NUMBERS,
    "fee_amount": _NUMBERS,
    "fee_currency": ("", "usd", "BTC", "EUR"),
    "source": ("", "income", "Gift", "MyBTC", "Interest", "Reward", "N/A", "Stolen"),
    "purpose": ("", "spent", "Gift", "Donation", "Lost", "Stolen"),
    "notes": ("", "=1+1", "a note"),
    "fee_usd": _NUMBERS,
    "fmv_usd": _NUMBERS,
    "broker_reporting": ("", "none", "Proceeds", "basis", "automatic", "weird"),
    "fee_usd_typed": ("", "yes", "no", "maybe"),
}

# Whole files with a bad shape.
CSV_BAD_FILES = {
    "empty": "",
    "header_only": "date,type,amount,from_account,to_account\n",
    "missing_column": "date,type,amount,from_account\n2024-01-01T10:00:00Z,Deposit,1,External\n",
    "extra_column": "date,type,amount,from_account,to_account,colour\n"
                    "2024-01-01T10:00:00Z,Deposit,100,External,Bank,red\n",
    "semicolons": "date;type;amount;from_account;to_account\n2024-01-01T10:00:00Z;Deposit;100;External;Bank\n",
    "bom": "﻿date,type,amount,from_account,to_account\n2024-01-01T10:00:00Z,Deposit,100,External,Bank\n",
    "sell_before_buy": "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd\n"
                       "2024-01-01T10:00:00Z,Sell,0.1,Exchange BTC,Exchange USD,,500\n"
                       "2024-01-01T10:00:00Z,Buy,0.1,Exchange USD,Exchange BTC,400,\n",
    "not_utf8": b"date,type,amount,from_account,to_account\n2024-01-01,Deposit,1,External,Bank\xff\n",
}

# River rows with a problem each, after the tests' synthetic rows.
RIVER_BAD_ROWS = (
    "not-a-date,25.00,USD,0.00030000,BTC,,,Buy",
    "2026-01-05 12:00:00,abc,USD,0.00030000,BTC,,,Buy",
    "2026-01-05 12:00:00,25.00,EUR,0.00030000,BTC,,,Buy",
    "2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Swap",
    "2026-01-05 12:00:00,,,,,,,",
)

# Entries as the MCP connector sends them (accounts by name).
ENTRY_BASE_ROWS = [
    {"date": "2025-07-01", "type": "Buy", "amount": "0.01", "from_account": "Bank",
     "to_account": "Exchange BTC", "cost_basis_usd": "1000", "fee_amount": "1", "fee_currency": "USD"},
    {"date": "2025-07-02T09:30:00", "type": "Deposit", "amount": "0.001", "from_account": "External",
     "to_account": "Wallet", "source": "Interest"},
    {"date": "2025-07-03T15:00:00Z", "type": "Withdrawal", "amount": "0.001", "from_account": "Wallet",
     "to_account": "External", "purpose": "Spent", "fee_amount": "0.00001", "fee_currency": "BTC"},
    {"date": "2025-07-04T15:00:00Z", "type": "Sell", "amount": "0.005", "from_account": "Exchange BTC",
     "to_account": "Exchange USD", "proceeds_usd": "600", "fee_amount": "1", "fee_currency": "USD"},
    {"date": "2025-07-05T15:00:00Z", "type": "Transfer", "amount": "0.005", "from_account": "Exchange BTC",
     "to_account": "Wallet", "fee_amount": "0.0001", "fee_currency": "BTC"},
]

ENTRY_CHANGES = (
    [("date", v) for v in ("", "yesterday", "2099-01-01", "07/01/2025", "2025-07-01T25:00:00")]
    + [("type", v) for v in ("buy", "Swap")]
    + [("amount", v) for v in ("0", "-1", "100")]
    + [("from_account", v) for v in ("bank", "Nowhere", "External")]
    + [("to_account", v) for v in ("wallet", "Nowhere", "External")]
    + [("cost_basis_usd", v) for v in ("-1", "0")]
    + [("proceeds_usd", v) for v in ("-1", "0")]
    + [("fee_currency", v) for v in ("EUR", "BTC")]
    + [("source", v) for v in ("Gift", "Stolen")]
    + [("purpose", v) for v in ("Gift", "Stolen")]
)

# MCP list_transactions filters.
MCP_LIST_FILTERS = (
    {},
    {"type": "Sell"},
    {"account": "Wallet"},
    {"start_date": "2024-01-01", "end_date": "2024-12-31"},
    {"limit": 3},
)
