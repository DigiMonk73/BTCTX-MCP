"""
BitcoinTX MCP server.

Lets an AI assistant add, find and correct transactions in a BitcoinTX
ledger from pasted text or plain English. Talks to a running BitcoinTX
instance over its REST API; run it locally over stdio from any MCP client.

Environment:
  BTCTX_URL          BitcoinTX base URL (default http://localhost:80)
  BTCTX_USERNAME     BitcoinTX login
  BTCTX_PASSWORD     BitcoinTX password
  BTCTX_VERIFY_TLS   "false" to accept a self-signed certificate
  BTCTX_CA_BUNDLE    path to a CA bundle for a private certificate
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Literal, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from btctx_mcp.client import BtctxClient, BtctxError
from btctx_mcp.guide import LEDGER_GUIDE

AccountName = Literal["Bank", "Wallet", "Exchange USD", "Exchange BTC", "External"]
TxTypeName = Literal["Buy", "Sell", "Deposit", "Withdrawal", "Transfer"]
DepositSource = Literal["MyBTC", "Gift", "Income", "Interest", "Reward"]
WithdrawalPurpose = Literal["Spent", "Gift", "Donation", "Lost"]

# Fixed account ids seeded by the app (backend/constants.py)
ACCOUNT_IDS: Dict[str, int] = {
    "Bank": 1, "Wallet": 2, "Exchange USD": 3, "Exchange BTC": 4,
    "BTC Fees": 5, "USD Fees": 6, "External": 99,
}
ACCOUNT_NAMES: Dict[int, str] = {v: k for k, v in ACCOUNT_IDS.items()}


class TransactionInput(BaseModel):
    """One transaction to preview or add. See the ledger guide for which fields each type needs."""
    date: str = Field(description="ISO 8601, e.g. 2024-03-05T14:30:00Z, or 2024-03-05 if the time is unknown.")
    type: TxTypeName
    amount: Decimal = Field(
        gt=0,
        description="BTC amount (max 8 decimals), or USD for Bank/Exchange USD cash moves. "
                    "Transfer: total that left the source INCLUDING the network fee. "
                    "Withdrawal: what the recipient got; the network fee is on top.",
    )
    from_account: AccountName
    to_account: AccountName
    cost_basis_usd: Optional[Decimal] = Field(
        default=None, description="Buy: USD spent excluding fee. Deposit: basis (auto-filled for Income/Interest/Reward).")
    proceeds_usd: Optional[Decimal] = Field(
        default=None, description="Sell: gross USD before fees. Withdrawal/Spent: USD value received (auto-filled if omitted).")
    fee_amount: Optional[Decimal] = Field(default=None, description="Fee amount; USD for Buy/Sell, BTC for on-chain moves.")
    fee_currency: Optional[Literal["BTC", "USD"]] = None
    source: Optional[DepositSource] = Field(default=None, description="Required for BTC deposits.")
    purpose: Optional[WithdrawalPurpose] = Field(default=None, description="Required for BTC withdrawals.")
    fmv_usd: Optional[Decimal] = Field(
        default=None, description="Gift/Donation withdrawals: fair market value (auto-filled if omitted).")


_client: Optional[BtctxClient] = None


def get_client() -> BtctxClient:
    global _client
    if _client is None:
        _client = BtctxClient.from_env()
    return _client


def set_client(client: Optional[BtctxClient]) -> None:
    """Inject a client (tests)."""
    global _client
    _client = client


async def _call(method: str, path: str, **kwargs: Any) -> Any:
    try:
        return await get_client().request(method, path, **kwargs)
    except BtctxError as exc:
        raise ToolError(str(exc)) from exc


def _rows(transactions: List[TransactionInput]) -> List[Dict[str, Any]]:
    if not transactions:
        raise ToolError("Provide at least one transaction.")
    return [t.model_dump(mode="json", exclude_none=True) for t in transactions]


def _parse_ts(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _parse_filter_date(value: Optional[str], end_of_day: bool) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = _parse_ts(value)
    except ValueError as exc:
        raise ToolError(f"Invalid date '{value}'. Use YYYY-MM-DD.") from exc
    if end_of_day and len(value) == 10:
        dt = dt.replace(hour=23, minute=59, second=59)
    return dt


def _compact(tx: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "id": tx["id"],
        "date": tx["timestamp"],
        "type": tx["type"],
        "amount": tx.get("amount"),
        "from": ACCOUNT_NAMES.get(tx.get("from_account_id"), tx.get("from_account_id")),
        "to": ACCOUNT_NAMES.get(tx.get("to_account_id"), tx.get("to_account_id")),
    }
    for key in ("fee_amount", "fee_currency", "source", "purpose", "cost_basis_usd",
                "proceeds_usd", "fmv_usd", "realized_gain_usd", "holding_period"):
        val = tx.get(key)
        if val not in (None, "", "N/A") and not (key == "fee_amount" and Decimal(str(val)) == 0):
            out[key] = val
    if tx.get("is_locked"):
        out["locked"] = True
    return out


mcp = MCPServer(
    name="bitcointx",
    title="BitcoinTX",
    description="Add and correct transactions in a self-hosted BitcoinTX Bitcoin tax ledger.",
    instructions=LEDGER_GUIDE,
)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


@mcp.tool(annotations=READ_ONLY)
def get_ledger_guide() -> str:
    """How to map exchange emails, wallet history and plain English onto BitcoinTX
    accounts, transaction types and tax fields. Read this before adding transactions."""
    return LEDGER_GUIDE


@mcp.tool(annotations=READ_ONLY)
async def get_portfolio() -> Dict[str, Any]:
    """Current balance of every account, average cost basis per BTC, and the live BTC price.
    Useful to reconcile against what the user's cold wallet or exchange actually shows."""
    balances = await _call("GET", "/api/calculations/accounts/balances")
    avg = await _call("GET", "/api/calculations/average-cost-basis")
    try:
        price = await _call("GET", "/api/bitcoin/price")
    except ToolError:
        price = None
    return {
        "balances": [
            {"account": b["name"], "currency": b["currency"], "balance": b["balance"]}
            for b in balances
        ],
        "average_cost_basis": avg,
        "btc_price_usd": price.get("USD") if isinstance(price, dict) else None,
    }


@mcp.tool(annotations=READ_ONLY)
async def list_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    type: Optional[TxTypeName] = None,
    account: Optional[AccountName] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    """Find recorded transactions, newest first. Filter by date range (YYYY-MM-DD, inclusive),
    type, and an account on either side. Use it to find an id before updating or deleting."""
    txs = await _call("GET", "/api/transactions")
    start = _parse_filter_date(start_date, end_of_day=False)
    end = _parse_filter_date(end_date, end_of_day=True)
    acct_id = ACCOUNT_IDS[account] if account else None

    matched = []
    for tx in txs:
        ts = _parse_ts(tx["timestamp"])
        if start and ts < start:
            continue
        if end and ts > end:
            continue
        if type and tx["type"] != type:
            continue
        if acct_id and acct_id not in (tx.get("from_account_id"), tx.get("to_account_id")):
            continue
        matched.append(tx)

    limit = max(1, min(limit, 500))
    return {
        "total_matching": len(matched),
        "returned": min(len(matched), limit),
        "transactions": [_compact(tx) for tx in matched[:limit]],
    }


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True))
async def get_btc_price(date: Optional[str] = None) -> Dict[str, Any]:
    """BTC price in USD for a date (YYYY-MM-DD, daily price) or right now if no date is given.
    Use it to value income, spending, or gifts when the user doesn't know the USD amount."""
    if date:
        data = await _call("GET", "/api/bitcoin/price/history", params={"date": date})
    else:
        data = await _call("GET", "/api/bitcoin/price")
    return {"date": date or "now", "usd": data.get("USD") if isinstance(data, dict) else data}


@mcp.tool(annotations=READ_ONLY)
async def preview_transactions(transactions: List[TransactionInput]) -> Dict[str, Any]:
    """Dry run: validate transactions, auto-fill missing USD values from historical prices,
    flag rows already in the ledger, and simulate the FIFO result (gain/loss, holding period,
    balances afterward). NOTHING is saved. Always call this and show the user the result
    before add_transactions."""
    return await _call("POST", "/api/import/entries/preview", json={"rows": _rows(transactions)})


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
async def add_transactions(transactions: List[TransactionInput]) -> Dict[str, Any]:
    """Save transactions to the ledger, all-or-nothing. Only call after preview_transactions and
    the user's confirmation. Rows exactly matching an existing transaction are skipped; rows
    previewed as possible_duplicate ARE saved, so drop any the user rejected."""
    return await _call("POST", "/api/import/entries/execute", json={"rows": _rows(transactions)})


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
async def update_transaction(
    transaction_id: int,
    date: Optional[str] = None,
    type: Optional[TxTypeName] = None,
    amount: Optional[Decimal] = None,
    from_account: Optional[AccountName] = None,
    to_account: Optional[AccountName] = None,
    cost_basis_usd: Optional[Decimal] = None,
    proceeds_usd: Optional[Decimal] = None,
    fee_amount: Optional[Decimal] = None,
    fee_currency: Optional[Literal["BTC", "USD"]] = None,
    source: Optional[DepositSource] = None,
    purpose: Optional[WithdrawalPurpose] = None,
    fmv_usd: Optional[Decimal] = None,
) -> Dict[str, Any]:
    """Change fields of one existing transaction (only the fields you pass). The whole ledger is
    recalculated, so gains on later sales may change. Confirm with the user first.
    Changing type or accounts requires passing type, from_account and to_account together."""
    changes: Dict[str, Any] = {}
    if date is not None:
        try:
            changes["timestamp"] = _parse_ts(date).isoformat()
        except ValueError as exc:
            raise ToolError(f"Invalid date '{date}'.") from exc
    if type is not None:
        changes["type"] = type
    if from_account is not None:
        changes["from_account_id"] = ACCOUNT_IDS[from_account]
    if to_account is not None:
        changes["to_account_id"] = ACCOUNT_IDS[to_account]
    for key, val in (("amount", amount), ("cost_basis_usd", cost_basis_usd),
                     ("fee_amount", fee_amount), ("fmv_usd", fmv_usd)):
        if val is not None:
            changes[key] = format(val, "f")
    if proceeds_usd is not None:
        changes["proceeds_usd"] = format(proceeds_usd, "f")
    if fee_currency is not None:
        changes["fee_currency"] = fee_currency
    if source is not None:
        changes["source"] = source
    if purpose is not None:
        changes["purpose"] = purpose
    if not changes:
        raise ToolError("No changes given.")

    needs_current = proceeds_usd is not None or any(
        k in changes for k in ("type", "from_account_id", "to_account_id"))
    current = await _call("GET", f"/api/transactions/{transaction_id}") if needs_current else None

    if any(k in changes for k in ("type", "from_account_id", "to_account_id")):
        # The server validates type rules against the full set; fill in what wasn't passed
        changes.setdefault("type", current["type"])
        changes.setdefault("from_account_id", current["from_account_id"])
        changes.setdefault("to_account_id", current["to_account_id"])
    if proceeds_usd is not None and changes.get("type", current["type"]) == "Sell":
        # Sells keep the gross so recalculation doesn't re-subtract the USD fee
        changes["gross_proceeds_usd"] = changes["proceeds_usd"]

    updated = await _call("PUT", f"/api/transactions/{transaction_id}", json=changes)
    return _compact(updated)


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
async def delete_transaction(transaction_id: int) -> Dict[str, Any]:
    """Permanently delete one transaction (locked transactions can't be deleted). The ledger is
    recalculated afterward. Confirm with the user first and tell them what you're deleting."""
    current = await _call("GET", f"/api/transactions/{transaction_id}")
    await _call("DELETE", f"/api/transactions/{transaction_id}")
    return {"deleted": _compact(current)}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
