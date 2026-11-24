"""
#953: a comma in a bitcoin amount is refused. A comma separates thousands
only in dollars: a spreadsheet that writes decimals with a comma writes 2.5
BTC as "2,500", which the thousands rule read as 2500 BTC, and "1,234" was
read as 1234 BTC with no error. BitcoinTX's own CSV import refuses a comma
in `amount` when the row's amount is bitcoin, and in `fee_amount` when its
fee is; River's import in each amount whose currency is BTC. Dollars keep
their thousands separator. (The exchange import's reader already refuses
any separator in bitcoin.)
"""

import csv
import io

from backend.services.csv_import import parse_csv_file
from backend.services.river_import import parse_river_csv

BTC_NOTE = ("A bitcoin amount takes no comma: write decimals with a point and no thousands separator"
            " (2.5 or 1234, not 2,5 or 1,234).")

WALLET_DEPOSIT = {"date": "2024-01-10T10:00:00Z", "type": "Deposit", "amount": "0.5", "from_account": "External",
                  "to_account": "Wallet", "cost_basis_usd": "100", "source": "MyBTC"}
BANK_DEPOSIT = {**WALLET_DEPOSIT, "to_account": "Bank", "cost_basis_usd": "", "source": "N/A"}
TRANSFER = {**WALLET_DEPOSIT, "type": "Transfer", "amount": "2", "from_account": "Exchange BTC",
            "cost_basis_usd": "", "source": "", "fee_amount": "0.0001", "fee_currency": "BTC"}
SPEND = {**WALLET_DEPOSIT, "type": "Withdrawal", "amount": "2", "from_account": "Wallet", "to_account": "External",
         "cost_basis_usd": "", "source": "", "purpose": "Spent", "proceeds_usd": "100", "fee_amount": "0.0001"}
BUY = {**WALLET_DEPOSIT, "type": "Buy", "from_account": "Bank", "to_account": "Exchange BTC", "source": "",
       "fee_amount": "5", "fee_currency": "USD"}

RIVER_HEADER = "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag"


def csv_file(*rows: dict) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]) + [c for c in ("fee_amount", "fee_currency", "purpose",
                                                                           "proceeds_usd") if c not in rows[0]],
                            quoting=csv.QUOTE_ALL)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return out.getvalue().encode()


def _errors(result) -> list[tuple[str | None, str]]:
    return [(e.column, e.message) for e in result.errors]


def test_a_bitcoin_amount_with_a_comma_is_refused():
    result = parse_csv_file(csv_file({**WALLET_DEPOSIT, "amount": "1,234"}))
    assert _errors(result) == [("amount", f"Invalid amount '1,234'. {BTC_NOTE}")]
    assert result.transactions == []


def test_a_decimal_comma_spreadsheets_2_5_bitcoin_is_refused():
    result = parse_csv_file(csv_file({**WALLET_DEPOSIT, "amount": "2,500"}))
    assert _errors(result) == [("amount", f"Invalid amount '2,500'. {BTC_NOTE}")]


def test_a_dollar_amount_keeps_its_thousands_separator():
    result = parse_csv_file(csv_file({**BANK_DEPOSIT, "amount": "1,234"}))
    assert result.errors == [], _errors(result)
    assert str(result.transactions[0]["amount"]) in ("1234", "1234.00", "1234.00000000")


def test_a_bitcoin_fee_with_a_comma_is_refused():
    result = parse_csv_file(csv_file({**TRANSFER, "fee_amount": "1,000"}))
    assert _errors(result) == [("fee_amount", f"Invalid fee_amount '1,000'. {BTC_NOTE}")]


def test_a_blank_fee_currency_that_is_bitcoin_counts_too():
    """A spend from a wallet pays its fee in bitcoin when fee_currency is blank."""
    result = parse_csv_file(csv_file({**SPEND, "fee_amount": "1,000"}))
    assert _errors(result) == [("fee_amount", f"Invalid fee_amount '1,000'. {BTC_NOTE}")]


def test_a_buys_fee_said_in_bitcoin_gets_the_buys_own_refusal():
    """A Buy pays its fee in dollars: a fee said in bitcoin is the type
    rule's to refuse, in its words, whatever its comma."""
    result = parse_csv_file(csv_file({**BUY, "fee_amount": "1,000", "fee_currency": "BTC"}))
    assert _errors(result) == [("fee_currency", "Buy fee must be in USD.")]


def test_a_dollar_fee_keeps_its_thousands_separator():
    result = parse_csv_file(csv_file({**BUY, "amount": "1", "cost_basis_usd": "100,000", "fee_amount": "1,000"}))
    assert result.errors == [], _errors(result)


def test_the_preview_and_the_import_refuse_it_and_save_nothing(auth_client):
    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    file = {"file": ("rows.csv", csv_file({**WALLET_DEPOSIT, "amount": "1,234"}), "text/csv")}
    preview = auth_client.post("/api/import/preview", files=file).json()
    assert preview["can_import"] is False
    assert [(e["column"], e["message"]) for e in preview["errors"]] == [("amount", f"Invalid amount '1,234'. {BTC_NOTE}")]
    assert auth_client.post("/api/import/execute", files=file).status_code == 400
    assert auth_client.get("/api/transactions").json() == []


def river_line(sent: str, sent_cur: str, received: str, received_cur: str, fee: str = "", fee_cur: str = "") -> bytes:
    return f'{RIVER_HEADER}\n2024-01-10 10:00:00,"{sent}",{sent_cur},"{received}",{received_cur},"{fee}",{fee_cur},Buy\n'.encode()


def test_rivers_bitcoin_amount_with_a_comma_is_refused():
    rows, errors = parse_river_csv(river_line("100000.00", "USD", "1,234", "BTC"))
    assert rows == []
    assert [(e.column, e.message) for e in errors] == [("Received Amount", f"Invalid Received Amount '1,234'. {BTC_NOTE}")]


def test_a_river_sends_fee_with_a_comma_is_refused_whatever_its_currency_column_says():
    """River records a send's fee in bitcoin (send()), so the comma is a bitcoin one."""
    for fee_currency in ("BTC", "", "USD"):
        rows, errors = parse_river_csv(river_line("1.5", "BTC", "", "", "1,000", fee_currency))
        assert rows == []
        assert [(e.column, e.message) for e in errors] == [("Fee Amount", f"Invalid Fee Amount '1,000'. {BTC_NOTE}")]


def test_a_river_sell_without_its_dollars_keeps_a_dollar_fee():
    """Tagged a Sell for dollars, the row is read as a Sell (its fee in
    dollars) even with Received Amount blank, never as a send."""
    rows, errors = parse_river_csv(river_line("1.5", "BTC", "", "USD", "1,000.00", "USD").replace(b",Buy", b",Sell"))
    assert errors == []


def test_a_river_sells_fee_is_in_dollars_whatever_its_currency_column_says():
    rows, errors = parse_river_csv(river_line("1.5", "BTC", "100000.00", "USD", "1,000", "BTC"))
    assert errors == []


def test_rivers_dollar_amounts_keep_their_thousands_separator():
    rows, errors = parse_river_csv(river_line("100,000.00", "USD", "1.5", "BTC", "1,000.00", "USD"))
    assert errors == []
    assert str(rows[0].sent) == "100000.00"
