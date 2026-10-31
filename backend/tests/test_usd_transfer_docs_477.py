"""
The CSV guide on a dollar transfer's fee (#477). BitcoinTX keeps a dollar
transfer (Bank <-> Exchange USD) as a withdrawal: its amount is what
arrived, the fee on top (`transaction._plain_lines`). The guide said a
transfer's amount is what left, fee included, which is true of bitcoin
only: "$1,000 sent, $990 arrived, a $10 fee" written as it said (amount
1000, fee 10) lowered the bank by $1,010 and raised Exchange USD by $1,000.
The guide now says so, and its example row imports to the balances its
title states.
"""

import re
from decimal import Decimal

from backend.services.csv_import import CSV_COLUMNS
from backend.tests.test_csv_instructions import SHIPPED, generator, text

BANK, EXCHANGE_USD, USD_FEES = 1, 3, 6
HEADER = ",".join(CSV_COLUMNS[:12])  # the examples give the template's first 12 columns
DOLLAR_EXAMPLE = re.compile(r"\$([\d,]+) left the bank, \$([\d,]+) arrived: amount ([\d,]+), the \$([\d,]+) fee on top")


def dollars(figure: str) -> Decimal:
    return Decimal(figure.replace(",", ""))


def test_the_guide_says_a_dollar_transfers_amount_is_what_arrived():
    guide = text(SHIPPED)
    assert "BTC Transfer: what left the account, fee included." in guide
    assert "USD Transfer (between dollar accounts): what arrived, fee on top." in guide  # by kind since 2.0 (#350)
    # The old words, for every transfer
    assert not re.search(r"(?<!BTC )Transfer: what left the account", guide)


def test_the_guides_dollar_example_imports_to_the_balances_it_states(auth_client):
    """An entry made as the guide says gives what its example says: the
    bank down by what left, the exchange up by what arrived, the rest the
    fee."""
    examples = [(title, row) for title, row in generator().EXAMPLES if ",Transfer," in row and ",Bank," in row]
    assert len(examples) == 1, "the guide has one dollar transfer example"
    title, row = examples[0]
    assert title in text(SHIPPED) and row in text(SHIPPED)
    left, arrived, amount, fee = map(dollars, DOLLAR_EXAMPLE.search(title).groups())
    assert (amount, fee) == (arrived, left - arrived)
    fields = dict(zip(CSV_COLUMNS, row.split(",")))
    assert (Decimal(fields["amount"]), Decimal(fields["fee_amount"]), fields["fee_currency"]) == (amount, fee, "USD")

    auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
    try:
        funds = "2024-01-01,Deposit,2000.00,External,Bank,,,,,,,"
        content = {"file": ("rows.csv", f"{HEADER}\n{funds}\n{row}\n".encode(), "text/csv")}
        r = auth_client.post("/api/import/execute", files=content)
        assert r.status_code == 200, r.text
        rows = auth_client.get("/api/calculations/accounts/balances").json()
        balance = {b["account_id"]: Decimal(str(b["balance"])) for b in rows}
        assert [balance[BANK], balance[EXCHANGE_USD], balance[USD_FEES]] == [2000 - left, arrived, fee]
    finally:
        auth_client.delete("/api/transactions/delete_all?confirm=DELETE")
