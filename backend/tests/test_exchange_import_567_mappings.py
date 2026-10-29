"""
Each ready-made mapping's sample file (B5b, #567): made-up rows in its
exchange's published format (testdata/exchange_files/), read into the rows
worked out here by hand from each format's rules:

- a Buy's cost basis is the dollars before the fee, its fee apart in
  dollars (the engine adds it to the basis, Treas. Reg. §1.1012-1(h)(1)),
  paid from the exchange's dollars when the file's earlier sales left
  enough there, else from the bank (#655);
- a Sell's proceeds are the dollars before the fee, its fee apart in dollars
  (the engine subtracts it, §1.1001-7(b)(2));
- a send is a Transfer of the coins that arrived, its network fee in
  bitcoin on top (River's rule); a receive a Transfer from the wallet;
- a payout a Deposit, valued at the file's value or the hour's price.

The file goes into the first exchange and wallet (1.x's 3, 4 and 2). Every
row not read is named by a warning; total_rows counts every row of data.
"""

import io
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from backend.tests.conftest import stub_daily_prices

FILES = Path(__file__).resolve().parents[2] / "testdata" / "exchange_files"
PRICE = 100000.0
EX_USD, EX_BTC, WALLET, BANK, EXTERNAL = "Exchange USD", "Exchange BTC", "Wallet", "Bank", "External"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    stub_daily_prices(monkeypatch, lambda day: PRICE)


@pytest.fixture
def client(auth_client):
    r = auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    assert r.status_code in (200, 204)
    return auth_client


def preview(client, mapping_id: str, name: str) -> dict:
    content = (FILES / name).read_bytes()
    r = client.post("/api/import/exchange/preview", data={"mapping_id": mapping_id},
                    files={"file": (name, io.BytesIO(content), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def at(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=timezone.utc)


def row(number, kind, from_, to, amount, when, cost=None, proceeds=None, fee=None, source=None):
    """A proposal as the test reads it: its figures as Decimals, its time in UTC."""
    currency = None if fee is None else "USD" if kind in ("Buy", "Sell") else "BTC"
    figures = (Decimal(amount), *(Decimal(v) if v is not None else None for v in (cost, proceeds, fee)))
    return (number, kind, from_, to, *figures, currency, source, when)


def rows(answer: dict) -> list:
    def number(v):
        return Decimal(v) if v is not None else None
    return [(p["row_number"], p["type"], p["from_account"], p["to_account"], number(p["amount"]),
             number(p["cost_basis_usd"]), number(p["proceeds_usd"]), number(p["fee_amount"]),
             p["fee_currency"], p["source"], datetime.fromisoformat(p["date"]).astimezone(timezone.utc))
            for p in answer["proposals"]]


def warned(answer: dict) -> str:
    return "\n".join(w["message"] for w in answer["warnings"])


def test_coinbase_transaction_history(client):
    """Built from Coinbase's published columns, not yet checked against a real export."""
    answer = preview(client, "coinbase", "coinbase_2024.csv")
    assert rows(answer) == [
        # Subtotal bought the coins; "Fees and/or Spread" apart (Total = 98.00 + 1.99)
        row(4, "Buy", BANK, EX_BTC, "0.001", at(2025, 1, 15, 14, 23, 11), cost="98.00", fee="1.99"),
        # Subtotal is the gross; 49.70 arrived after the 0.30 fee
        row(5, "Sell", EX_BTC, EX_USD, "0.0005", at(2025, 2, 1, 10), proceeds="50.00", fee="0.30"),
        row(6, "Transfer", EX_BTC, WALLET, "0.0003", at(2025, 2, 2, 10)),
        row(7, "Transfer", WALLET, EX_BTC, "0.0002", at(2025, 2, 3, 10)),
        # Rewards at Coinbase's value at receipt (its 1099-MISC's)
        row(8, "Deposit", EXTERNAL, EX_BTC, "0.000003", at(2025, 2, 4, 10), cost="0.30", source="Reward"),
        row(9, "Deposit", EXTERNAL, EX_BTC, "0.00001", at(2025, 2, 5, 10), cost="1.00", source="Income"),
    ]
    assert answer["total_rows"] == 11 and answer["errors"] == []
    said = warned(answer)
    for expected in ("Rows 10 and 11 trade bitcoin for another asset (“Convert”)", "Row 12 is ETH, not bitcoin",
                     "Row 13 moves dollars, not bitcoin (“Deposit”)", "Row 14 is “Pro Withdrawal”, which this mapping "
                     "leaves out"):
        assert expected in said, (expected, said)


def test_coinbase_transaction_history_before_2024(client):
    answer = preview(client, "coinbase", "coinbase_2022.csv")
    assert rows(answer) == [
        row(7, "Buy", BANK, EX_BTC, "0.002", at(2022, 3, 1, 15), cost="86.00", fee="1.99"),
        row(8, "Sell", EX_BTC, EX_USD, "0.001", at(2022, 4, 1, 15), proceeds="45.00", fee="0.67"),
    ]


def test_coinbase_a_buys_basis_is_its_total_and_a_sales_proceeds_what_arrived(client):
    """Coinbase's file of 13 columns (#789, T3's evidence): a Buy's or Sell's
    "Fees and/or Spread" is a spread, not its fee, so Subtotal and it
    don't make the Total. What left or arrived is the Total: its fee is
    the gap between it and Subtotal. Read as Subtotal plus that cell, the
    buy's basis was $33.01 and the sale's net proceeds $16.15."""
    answer = preview(client, "coinbase", "coinbase_2026.csv")
    assert rows(answer) == [
        # $35.00 paid: Subtotal $32.85, its fee the $2.15 gap
        row(5, "Buy", BANK, EX_BTC, "0.0004", at(2026, 2, 1, 10), cost="32.85", fee="2.15"),
        # $15.91 arrived: Subtotal $16.40 the gross, its fee the $0.49 gap
        row(6, "Sell", EX_BTC, EX_USD, "0.0002", at(2026, 3, 1, 10), proceeds="16.40", fee="0.49"),
        # Total = Subtotal: no fee, never the 0.05 spread beside them (paid from the sale's dollars, #655)
        row(7, "Buy", EX_USD, EX_BTC, "0.0001", at(2026, 3, 15, 10), cost="8.00"),
        # A reward's value at receipt is Subtotal, the coins at the price, never Total
        row(8, "Deposit", EXTERNAL, EX_BTC, "0.0000037", at(2026, 3, 20, 10), cost="0.30", source="Reward"),
        # A buy for less than Subtotal, a sale for more: what was paid or arrived, and no fee made up
        row(9, "Buy", BANK, EX_BTC, "0.000125", at(2026, 3, 25, 10), cost="9.90"),  # $7.91 left at Coinbase: the bank
        row(10, "Sell", EX_BTC, EX_USD, "0.0002", at(2026, 3, 30, 10), proceeds="16.50"),
    ]
    assert answer["errors"] == []


def test_coinbase_advance_trade_and_reward_income(client):
    """Coinbase also writes "Advance Trade Buy/Sell" (no "d") and "Reward
    Income" (#765: BittyTax's parser and other open-source fixtures read
    them); each was left out as a kind the mapping doesn't read."""
    answer = preview(client, "coinbase", "coinbase_advance_trade.csv")
    assert rows(answer) == [
        row(4, "Buy", BANK, EX_BTC, "0.001", at(2025, 3, 18, 11, 49, 37), cost="80.00", fee="0.48"),
        row(5, "Sell", EX_BTC, EX_USD, "0.0005", at(2025, 3, 19, 11, 49, 37), proceeds="41.00", fee="0.25"),
        # Income at Coinbase's value at receipt, as its other rewards
        row(6, "Deposit", EXTERNAL, EX_BTC, "0.00001", at(2025, 3, 20, 11, 49, 37), cost="0.82", source="Reward"),
    ]
    assert answer["errors"] == [] and "left out" not in warned(answer)


def test_coinbase_transaction_history_with_its_older_fee_column(client):
    """An older "Transaction history" names the total "Total (inclusive of
    fees)" and its fee column "Fees" (#765); the file was refused."""
    answer = preview(client, "coinbase", "coinbase_2021.csv")
    assert rows(answer) == [
        row(2, "Buy", BANK, EX_BTC, "0.002", at(2021, 5, 3, 15), cost="110.00", fee="1.99"),
        row(3, "Sell", EX_BTC, EX_USD, "0.001", at(2021, 6, 1, 15), proceeds="36.00", fee="0.53"),
    ]


def test_kraken_ledger(client):
    answer = preview(client, "kraken", "kraken_ledgers.csv")
    assert rows(answer) == [
        # A trade's two lines: 500 dollars and their 1.30 fee for 0.005 BTC, from the bank: no
        # sale before it left the exchange dollars (#655; the file's dollar deposit isn't read)
        row(4, "Buy", BANK, EX_BTC, "0.005", at(2025, 1, 3, 10, 15, 30), cost="500.00", fee="1.30"),
        # 0.002 BTC sold for 210 dollars, its 0.55 fee taken from them
        row(5, "Sell", EX_BTC, EX_USD, "0.002", at(2025, 2, 10, 8), proceeds="210.00", fee="0.55"),
        # Buy Crypto's spend and receive: $101.49 from the sale's $209.45, so from the exchange's dollars
        row(8, "Buy", EX_USD, EX_BTC, "0.00098", at(2025, 2, 15, 12, 30), cost="100.00", fee="1.49"),
        # A withdrawal: the amount sent, its fee on top (the pending copy above it left out)
        row(10, "Transfer", EX_BTC, WALLET, "0.002", at(2025, 3, 1, 9, 5), fee="0.000015"),
        row(11, "Transfer", WALLET, EX_BTC, "0.001", at(2025, 3, 5, 18, 45)),
        # An earn reward, to the satoshi, valued at the hour's price: 0.00000123 × 100,000
        row(14, "Deposit", EXTERNAL, EX_BTC, "0.00000123", at(2025, 3, 13), cost="0.12", source="Reward"),
    ]
    assert answer["total_rows"] == 20 and answer["errors"] == []
    said = warned(answer)
    for expected in ("Rows 2 and 21 move dollars", "Row 9 is Kraken's pending copy",
                     "Rows 12 and 13 move coins between Kraken's own balances",
                     "0.0000012345 BTC is rounded to 0.00000123 BTC", "Rows 15 and 16 are ETH, not bitcoin",
                     "Rows 17 and 18 trade bitcoin for ETH", "Rows 19 and 20 are a withdrawal Kraken sent back"):
        assert expected in said, (expected, said)


def test_kraken_trades_paid_with_fee_credits(client):
    """A fee Kraken's fee credits paid is a third line of the trade's, KFEE,
    moving nothing (#829): the trade is read from its bitcoin and dollar
    lines, the credits are no dollars of the owner's, never another coin
    the bitcoin was traded for."""
    answer = preview(client, "kraken", "kraken_fee_credits.csv")
    assert rows(answer) == [
        # 200 dollars for 0.002 BTC, the whole fee paid in credits: the cost is what was paid, no fee
        row(5, "Buy", BANK, EX_BTC, "0.002", at(2025, 5, 2, 10), cost="200.00"),
        # 0.001 BTC sold for 105 dollars, the last 30 credits paying part of its fee: only the 0.12 the
        # dollars paid is a fee
        row(6, "Sell", EX_BTC, EX_USD, "0.001", at(2025, 5, 3, 11), proceeds="105.00", fee="0.12"),
    ]
    assert answer["total_rows"] == 7 and answer["errors"] == []
    said = warned(answer)
    assert "Row 2 is KFEE, not bitcoin" in said  # the credits arriving
    assert ("Rows 5 and 6 paid a fee with Kraken fee credits (KFEE), which aren't your money: the credits count as "
            "no fee.") in said
    assert "trade bitcoin for KFEE" not in said


def test_kraken_fee_credits_paying_a_fee_of_their_own_or_unreadable(client):
    """Fee credits alone pay a fee of their own (a margin rollover's): never
    "dollars"; a KFEE line whose amount can't be read is left out with its
    event as another asset, its numbers unread, never an error (#829)."""
    header = '"txid","refid","time","type","subtype","aclass","asset","wallet","amount","fee","balance"\n'
    content = header + (
        '"LC1","RC1","2025-06-01 00:00:00","rollover","","currency","KFEE","spot / main",0.00,5.00,25.00\n'
        '"LC2","TC1","2025-06-02 00:00:00","transfer","","currency","KFEE","spot / main",abc,0.00,25.00\n'
        '"LC3","TC1","2025-06-02 00:00:00","transfer","","currency","BTC","spot / main",0.0010000000,0,0.001\n'
        # Credits never pay a withdrawal's fee (Kraken): a stray KFEE line beside one leaves its send as it is
        '"LC4","WC1","2025-06-03 00:00:00","withdrawal","","currency","BTC","spot / main",-0.0005000000,0.00001,0.00049\n'
        '"LC5","WC1","2025-06-03 00:00:00","withdrawal","","currency","KFEE","spot / main",0.00,0.00,25.00\n')
    r = client.post("/api/import/exchange/preview", data={"mapping_id": "kraken"},
                    files={"file": ("ledgers.csv", io.BytesIO(content.encode()), "text/csv")})
    assert r.status_code == 200, r.text
    answer = r.json()
    assert rows(answer) == [row(5, "Transfer", EX_BTC, WALLET, "0.0005", at(2025, 6, 3), fee="0.00001")]
    assert answer["errors"] == []
    said = warned(answer)
    assert "Row 2 is a fee paid with Kraken fee credits (KFEE), not bitcoin: left out." in said
    assert "moves dollars" not in said
    assert "Rows 3 and 4 move coins between Kraken's own balances" in said
    # The fee-credit note is a trade's: a send's bitcoin fee counts
    assert not [w for w in answer["warnings"] if w["message"].startswith("Row 5 ") and "fee credits" in w["message"]]


def test_strike_statement(client):
    answer = preview(client, "strike", "strike_statement.csv")
    assert rows(answer) == [
        # 101 dollars debited, the 1.00 fee in them: 100.00 bought the coins
        row(3, "Buy", BANK, EX_BTC, "0.001", at(2025, 1, 6, 15, 30), cost="100.00", fee="1.00"),
        # 49.50 arrived after the 0.50 fee: proceeds of 50.00
        row(4, "Sell", EX_BTC, EX_USD, "0.0005", at(2025, 2, 11, 9, 10, 11), proceeds="50.00", fee="0.50"),
        row(5, "Transfer", EX_BTC, WALLET, "0.0003", at(2025, 2, 12, 10), fee="0.000005"),
        row(6, "Transfer", WALLET, EX_BTC, "0.0002", at(2025, 2, 13, 10)),
        # A target order's two pieces, one id: 200 dollars (2.00 fee in them) at
        # 08:00, the coins at 08:05, one buy dated by its coins; more than the
        # sale's $49.50 left, so from the bank
        row(8, "Buy", BANK, EX_BTC, "0.00198", at(2025, 3, 1, 8, 5), cost="198.00", fee="2.00"),
    ]
    assert answer["total_rows"] == 11 and answer["errors"] == []
    said = warned(answer)
    for expected in ("Row 2 moves dollars, not bitcoin (“Deposit”)", "Rows 9 and 10 were reversed or cancelled",
                     "Row 11 moves dollars, not bitcoin (“Withdrawal”)",
                     "Row 12 is “Bitcoin Back”, a kind of row this mapping doesn't read"):
        assert expected in said, (expected, said)


def test_strike_activity_report(client):
    answer = preview(client, "strike", "strike_activity.csv")
    assert rows(answer) == [row(2, "Buy", BANK, EX_BTC, "0.00025", at(2025, 4, 1, 16, 20), cost="25.00", fee="0.25")]
    said = warned(answer)
    assert "Row 3 is Pending, not completed" in said and "Row 4 is Reversed, not completed" in said


def test_swan_deposits_and_purchases(client):
    answer = preview(client, "swan", "swan_deposits_and_purchases.csv")
    assert rows(answer) == [
        # Swan pulls a buy's dollars from the bank; Transaction USD bought the coins, the fee apart
        row(5, "Buy", BANK, EX_BTC, "0.0011", at(2025, 3, 3, 14, 5, 10), cost="99.00", fee="1.00"),
        row(6, "Buy", BANK, EX_BTC, "0.00055", at(2025, 3, 10, 14, 5, 10), cost="50.00"),
        row(9, "Transfer", WALLET, EX_BTC, "0.002", at(2025, 3, 19, 9)),
    ]
    assert answer["total_rows"] == 7 and answer["errors"] == []
    said = warned(answer)
    for expected in ("Row 4 moves dollars, not bitcoin (“deposit”)", "Row 7 is pending, not completed",
                     "Row 8 is Swan moving coins between its custodians", "Row 10 moves dollars"):
        assert expected in said, (expected, said)


def test_swan_withdrawals(client):
    answer = preview(client, "swan-withdrawals", "swan_withdrawals.csv")
    # Swan's custodian pays the network fee: what left is what arrived
    assert rows(answer) == [row(4, "Transfer", EX_BTC, WALLET, "0.0015", at(2025, 3, 20, 10, 30))]
    said = warned(answer)
    assert "Row 5 was canceled" in said and "Row 6 hasn't been sent" in said


def test_cash_app_bitcoin_transactions(client):
    answer = preview(client, "cash-app", "cash_app_bitcoin.csv")
    assert rows(answer) == [
        # Each date in the account's US zone: 09:15 EST is 14:15 UTC
        row(2, "Buy", BANK, EX_BTC, "0.001", at(2025, 1, 10, 14, 15), cost="98.15", fee="2.00"),
        row(3, "Buy", BANK, EX_BTC, "0.0001", at(2025, 2, 1, 14, 15), cost="9.80", fee="0.20"),
        # 12:00 PDT is 19:00 UTC; the Amount is the gross, the fee apart
        row(4, "Sell", EX_BTC, EX_USD, "0.0005", at(2025, 7, 4, 19), proceeds="50.00", fee="1.49"),
        # Its fee was in dollars: a send's fee is bitcoin, so it isn't read
        row(5, "Transfer", EX_BTC, WALLET, "0.0002", at(2025, 7, 5, 15)),
        # A Boost: card cash-back in bitcoin, a rebate at the value Cash App gives it
        row(6, "Deposit", EXTERNAL, EX_BTC, "0.000005", at(2025, 7, 6, 15), cost="0.50", source="Rebate"),
        row(7, "Transfer", WALLET, EX_BTC, "0.0001", at(2025, 7, 7, 15)),
    ]
    assert answer["total_rows"] == 7 and answer["errors"] == []
    said = warned(answer)
    assert "This send's fee is $2.00: BitcoinTX records a send's fee in BTC, so it isn't read" in said
    assert "Row 8 is “Bitcoin Payment”, a kind of row this mapping doesn't read" in said


def test_cash_app_activity(client):
    answer = preview(client, "cash-app", "cash_app_activity.csv")
    assert rows(answer) == [
        row(2, "Buy", BANK, EX_BTC, "0.01", at(2025, 8, 1, 15), cost="1000.00", fee="10.00"),
    ]
    said = warned(answer)
    assert "Row 3 is FAILED, not completed" in said and "Row 4 isn't bitcoin (its asset is blank)" in said


def test_a_boosts_value_is_kept_as_typed_and_a_payout_without_one_is_priced(client):
    """A file's own value at receipt is the exchange's (on its 1099-MISC);
    without one, the hour's price fills it, marked as from the price."""
    boost = next(p for p in preview(client, "cash-app", "cash_app_bitcoin.csv")["proposals"] if p["source"] == "Rebate")
    reward = next(p for p in preview(client, "kraken", "kraken_ledgers.csv")["proposals"] if p["source"] == "Reward")
    assert (boost["basis_autofilled"], reward["basis_autofilled"]) == (False, True)


@pytest.mark.parametrize("mapping_id, name", [
    ("kraken", "strike_statement.csv"), ("strike", "kraken_ledgers.csv"), ("cash-app", "swan_withdrawals.csv"),
])
def test_another_exchanges_file_is_said_to_be_one(client, mapping_id, name):
    answer = preview(client, mapping_id, name)
    assert answer["proposals"] == [] and "This does not look like" in answer["errors"][0]["message"]


@pytest.mark.parametrize("name, expected", [
    ("coinbase_2024.csv", "coinbase"), ("coinbase_2022.csv", "coinbase"), ("coinbase_2021.csv", "coinbase"),
    ("coinbase_advance_trade.csv", "coinbase"), ("coinbase_2026.csv", "coinbase"), ("kraken_ledgers.csv", "kraken"), ("strike_statement.csv", "strike"), ("strike_activity.csv", "strike"),
    ("swan_deposits_and_purchases.csv", "swan"), ("swan_withdrawals.csv", "swan-withdrawals"),
    ("cash_app_bitcoin.csv", "cash-app"), ("cash_app_activity.csv", "cash-app"),
])
def test_the_columns_route_says_which_exchanges_file_it_is(client, name, expected):
    r = client.post("/api/import/exchange/columns", files={"file": (name, (FILES / name).read_bytes(), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["looks_like"] == expected
