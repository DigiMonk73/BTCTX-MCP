"""
The AI's guide on a dollar transfer's fee (#477). BitcoinTX keeps a dollar
transfer (Bank <-> Exchange USD) as a withdrawal: its amount is what
arrived, the fee on top (`transaction._plain_lines`). The guide, and the
connector's description of `amount`, said a transfer's amount is what left,
fee included, which is true of bitcoin only: "$1,000 sent, $990 arrived, a
$10 fee" sent as they said (amount 1000, fee 10) lowered the bank by $1,010
and raised Exchange USD by $1,000. Both now say so, and the guide's example
added through the connector gives the balances it states.
"""

import json
import re
from decimal import Decimal

import pytest

from btctx_mcp.guide import LEDGER_GUIDE
from test_server import backend_db, call, mcp_client  # noqa: F401  (fixtures)

pytestmark = pytest.mark.anyio

FLAT = " ".join(LEDGER_GUIDE.split())
DOLLAR_EXAMPLE = re.compile(
    r"\$([\d,]+) left the bank and \$([\d,]+) arrived at the exchange \(a \$([\d,]+) fee\) -> "
    r"amount ([\d,]+), fee_amount ([\d,]+), fee_currency USD: "
    r"the bank goes down \$([\d,]+), the exchange's USD account up \$([\d,]+)\.")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def dollars(figure: str) -> Decimal:
    return Decimal(figure.replace(",", ""))


def test_the_guide_says_a_dollar_transfers_amount_is_what_arrived():
    assert "Bitcoin: amount = total that LEFT the source, network fee INCLUDED" in FLAT
    assert ("Dollars (a bank <-> an exchange's USD account) are the other way round, as for a Withdrawal: "
            "amount = what ARRIVED, and the fee (fee_currency USD) is ON TOP") in FLAT
    # The old words, for every transfer
    assert "Bank <-> Exchange USD. amount = total that LEFT" not in FLAT


async def test_the_connector_describes_a_dollar_transfers_amount(mcp_client):  # noqa: F811
    """The tools' own description of `amount`, which the AI reads too."""
    tools = {t.name: json.dumps(t.input_schema) for t in (await mcp_client.list_tools()).tools}
    for name in ("preview_transactions", "add_transactions"):
        assert "USD Transfer (a bank <-> an exchange's USD account): what arrived; the fee is on top." in tools[name]
        assert "BTC Transfer: total that left the source INCLUDING the network fee" in tools[name]


async def test_the_guides_dollar_example_gives_the_balances_it_states(mcp_client):  # noqa: F811
    """An entry made as the guide says gives what its example says."""
    left, arrived, fee, amount, fee_amount, down, up = map(dollars, DOLLAR_EXAMPLE.search(FLAT).groups())
    assert (left - arrived, down, up) == (fee, left, arrived)  # the example adds up
    await call(mcp_client, "add_transactions", {"transactions": [
        {"date": "2024-03-01T10:00:00Z", "type": "Deposit", "amount": "2000.00",
         "from_account": "External", "to_account": "Bank"},
        {"date": "2024-03-02T10:00:00Z", "type": "Transfer", "amount": str(amount),
         "from_account": "Bank", "to_account": "Exchange USD",
         "fee_amount": str(fee_amount), "fee_currency": "USD"},
    ]})
    portfolio = await call(mcp_client, "get_portfolio")
    balance = {b["account"]: Decimal(b["balance"]) for b in portfolio["balances"]}
    assert [balance["Bank"], balance["Exchange USD"]] == [2000 - down, up]
