"""
BitcoinTX MCP server.

Lets an AI assistant add, find and correct transactions in a BitcoinTX
ledger from pasted text or plain English. Talks to a running BitcoinTX
instance over its REST API; run it locally over stdio from any MCP client.

Environment (none needed for the Mac app: without BTCTX_AI_KEY the server
reads the app's AI key file):
  BTCTX_URL          BitcoinTX base URL (default http://localhost:80)
  BTCTX_AI_KEY       the AI key created in BitcoinTX Settings (Docker, StartOS)
  BTCTX_MCP_FILE     the Mac app's key file, if not in the default place
                     (~/Library/Application Support/BitcoinTX/mcp.json)
  BTCTX_VERIFY_TLS   "false" to accept a self-signed certificate
  BTCTX_CA_BUNDLE    path to a CA bundle for a private certificate
BTCTX_PASSWORD is no longer used: while it is set, every tool says to replace
it with BTCTX_AI_KEY (btctx_mcp/client.py).
"""

from __future__ import annotations

import functools
import importlib.metadata
import inspect
import logging
from datetime import datetime, time, timezone, tzinfo
from decimal import Decimal
from typing import Annotated, Any, Dict, Literal  # noqa: UP035 (ToolResult)
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from btctx_mcp.client import BtctxClient, BtctxError
from btctx_mcp.guide import LEDGER_GUIDE

# What a tool returns. typing.Dict, not dict: the MCP SDK describes a Dict
# result as {"result": {...}} in the tool's output schema and structured
# output, a dict as the object itself. The released connectors have the
# first shape, and an MCP client may rely on it.
ToolResult = Dict[str, Any]  # noqa: UP006

AccountName = Literal["Bank", "Wallet", "Exchange USD", "Exchange BTC", "External"]
TxTypeName = Literal["Buy", "Sell", "Deposit", "Withdrawal", "Transfer"]
DepositSource = Literal["MyBTC", "Gift", "Inherited", "Income", "Interest", "Reward", "Rebate"]
WithdrawalPurpose = Literal["Spent", "Gift", "Donation", "Lost"]

# Fixed account ids seeded by the app (backend/constants.py)
ACCOUNT_IDS: dict[str, int] = {
    "Bank": 1, "Wallet": 2, "Exchange USD": 3, "Exchange BTC": 4,
    "BTC Fees": 5, "USD Fees": 6, "External": 99,
}
ACCOUNT_NAMES: dict[int, str] = {v: k for k, v in ACCOUNT_IDS.items()}

# The largest values BitcoinTX takes (backend/schemas/transaction.py, what
# its database holds): 10 digits before the point for an amount or a fee,
# 16 for a USD value. One over them is refused here, before any request.
AMOUNT_LIMIT = Decimal(10) ** 10
USD_LIMIT = Decimal(10) ** 16
AmountValue = Annotated[Decimal, Field(lt=AMOUNT_LIMIT)]
UsdValue = Annotated[Decimal, Field(lt=USD_LIMIT)]


class TransactionInput(BaseModel):
    """One transaction to preview or add. See the ledger guide for which fields each type needs."""
    date: str = Field(description="ISO 8601, e.g. 2024-03-05T14:30:00Z, or 2024-03-05 if the time is unknown.")
    type: TxTypeName
    amount: AmountValue = Field(
        gt=0,
        description="BTC amount (max 8 decimals), or USD for Bank/Exchange USD cash moves. "
                    "Transfer: total that left the source INCLUDING the network fee (Wallet to Wallet, "
                    "a consolidation: only the fee is recorded). "
                    "Withdrawal: what the recipient got; the network fee is on top.",
    )
    from_account: AccountName
    to_account: AccountName
    cost_basis_usd: UsdValue | None = Field(
        default=None, description="Buy: USD spent excluding fee. Deposit: basis (auto-filled for Income/Interest/Reward/Rebate, "
                                  "and for Inherited from the date of death).")
    proceeds_usd: UsdValue | None = Field(
        default=None, description="Sell: gross USD before fees. Withdrawal/Spent: USD value received (auto-filled if omitted).")
    fee_amount: AmountValue | None = Field(default=None, description="Fee amount; USD for Buy/Sell, BTC for on-chain moves.")
    fee_currency: Literal["BTC", "USD"] | None = None
    source: DepositSource | None = Field(default=None, description="Required for BTC deposits.")
    purpose: WithdrawalPurpose | None = Field(default=None, description="Required for BTC withdrawals.")
    fmv_usd: UsdValue | None = Field(
        default=None, description="Gift/Donation/Lost withdrawals: fair market value when it left "
                                  "(that hour's price x amount if omitted).")
    fee_usd: UsdValue | None = Field(
        default=None, description="A BTC network fee's USD value, if the user knows it (otherwise fee x the "
                                  "price when its hour began is stored).")
    acquired_at: str | None = Field(
        default=None, description="MyBTC/Gift deposits into Wallet or Exchange BTC: when the coins were originally "
                                  "acquired (for a gift, by the giver), e.g. 2021-03-14. The holding period and "
                                  "Form 8949's date acquired use it; omitted, the deposit's date. Inherited "
                                  "deposits: the date of death (required).")
    not_a_duplicate: bool | None = Field(
        default=None, description="true only when the user says this row is another transaction than the one "
                                  "preview_transactions matched as a duplicate: it's then saved, once (sent "
                                  "again, it's left out). Never set it on your own.")


_client: BtctxClient | None = None


def get_client() -> BtctxClient:
    global _client
    if _client is None:
        _client = BtctxClient.from_env()
    return _client


def set_client(client: BtctxClient | None) -> None:
    """Inject a client (tests)."""
    global _client
    _client = client


# Version check: the connector and BitcoinTX should be the same release
def connector_version() -> str | None:
    try:
        return importlib.metadata.version("btctx-mcp")
    except importlib.metadata.PackageNotFoundError:  # run from a source tree
        return None


def _release(version: str) -> tuple | None:
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def mismatch_notice(connector: str | None, app: str | None) -> str | None:
    """The line every tool reply starts with when the versions differ."""
    if not connector or not app or connector == app:
        return None
    head = f"Your BitcoinTX connector is v{connector} but BitcoinTX is v{app}."
    c, a = _release(connector), _release(app)
    if c and a and c > a:
        return f"{head} Update BitcoinTX, or set the connector back to v{app} in your AI app's settings."
    return (f"{head} In your AI app's settings, change btctx-mcp=={connector} in its uvx command "
            f"to btctx-mcp=={app}, then restart the AI app.")


_version = {"checked": False, "notice": None}


async def _version_notice() -> str | None:
    """Checked once BitcoinTX answers (so a BitcoinTX that was down at first is
    checked on a later call); a warning only, the tool still runs."""
    if not _version["checked"]:
        app = await get_client().app_version()
        if app is not None:
            _version.update(checked=True, notice=mismatch_notice(connector_version(), app))
    return _version["notice"]


def with_version_notice(fn):
    """Put the version notice first in the tool's reply (or error)."""
    @functools.wraps(fn)
    async def tool(*args: Any, **kwargs: Any) -> Any:
        try:
            result = fn(*args, **kwargs)
            if inspect.isawaitable(result):
                result = await result
        except ToolError as exc:
            notice = await _version_notice()
            raise ToolError(f"{notice}\n\n{exc}" if notice else str(exc)) from exc
        notice = await _version_notice()
        if notice and isinstance(result, str):
            return f"{notice}\n\n{result}"
        if notice and isinstance(result, dict):
            return {"notice": notice, **result}
        return result
    return tool


async def _call(method: str, path: str, **kwargs: Any) -> Any:
    try:
        return await get_client().request(method, path, **kwargs)
    except BtctxError as exc:
        raise ToolError(str(exc)) from exc


def _rows(transactions: list[TransactionInput]) -> list[dict[str, Any]]:
    if not transactions:
        raise ToolError("Provide at least one transaction.")
    return [t.model_dump(mode="json", exclude_none=True) for t in transactions]


def _parse_ts(value: str) -> datetime:
    """A timestamp BitcoinTX sent (stored in UTC)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# Besides ISO 8601, the formats add_transactions reads (the list in
# backend/services/csv_import.py, _DATE_FORMATS): (format, date only).
_OTHER_DATE_FORMATS = (
    ("%Y-%m-%dT%H:%M:%SZ", False), ("%Y-%m-%dT%H:%M:%S%z", False), ("%Y-%m-%d %H:%M:%S UTC", False),
    ("%Y-%m-%dT%H:%M:%S", False), ("%Y-%m-%d %H:%M:%S", False), ("%Y-%m-%d", True),
    ("%m/%d/%Y %H:%M:%S", False), ("%m/%d/%Y", True),
)


def _parse_date_text(raw: str) -> tuple[datetime, bool] | None:
    """(the date, whether it is a date alone), or None if it isn't one. Naive
    when no timezone is stated. Same reading as add_transactions
    (backend/services/entry_import.py, _normalize_date)."""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")), len(raw) <= 10 and ":" not in raw
    except ValueError:
        pass
    for fmt, date_only in _OTHER_DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if fmt.endswith(("Z", " UTC")):
            dt = dt.replace(tzinfo=timezone.utc)
        return dt, date_only
    return None


async def _tax_zone() -> tzinfo:
    """The user's tax timezone (BitcoinTX Settings): dates without a timezone are read in it."""
    data = await _call("GET", "/api/settings/tax-timezone")
    name = (data.get("timezone") if isinstance(data, dict) else None) or "UTC"
    if name == "UTC":
        return timezone.utc
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ToolError(f"This computer's timezone data doesn't know the tax timezone {name}; "
                        "update the connector (btctx-mcp) or its tzdata package.") from exc


def _in_utc(parsed: tuple[datetime, bool], zone: tzinfo, bare_date_at: time) -> datetime:
    """A parsed date in UTC: without a timezone it is in `zone`, and a date
    alone is at `bare_date_at` there (midday for a transaction)."""
    dt, date_only = parsed
    if dt.tzinfo is None:
        dt = datetime.combine(dt.date(), bare_date_at, tzinfo=zone) if date_only else dt.replace(tzinfo=zone)
    return dt.astimezone(timezone.utc)


def _parse_filter_date(value: str | None) -> tuple[datetime, bool] | None:
    if not value:
        return None
    parsed = _parse_date_text(value.strip())
    if parsed is None:
        raise ToolError(f"Invalid date '{value}'. Use YYYY-MM-DD.")
    return parsed


def _from_price(tx: dict[str, Any]) -> dict[str, Any] | None:
    """Which values BitcoinTX filled in from a price, and that price: its hour or day
    (UTC), source and USD per BTC, as the preview and add answers give them (#208).
    From the API's values_from_price and price_used (services/transaction.py)."""
    values = tx.get("values_from_price") or []
    return {"values": values, **(tx.get("price_used") or {})} if values else None


def _balance(account: dict[str, Any]) -> Any:
    """A BTC account's balance with all eight places ("0.00000005"): the API gives a
    number, which JSON writes as 5e-08 under 0.0001 (#101). A dollar balance as given."""
    return f"{account['balance']:.8f}" if account.get("currency") == "BTC" else account["balance"]


def _compact(tx: dict[str, Any]) -> dict[str, Any]:
    out = {
        "id": tx["id"],
        "date": tx["timestamp"],
        "type": tx["type"],
        "amount": tx.get("amount"),
        "from": ACCOUNT_NAMES.get(tx.get("from_account_id"), tx.get("from_account_id")),
        "to": ACCOUNT_NAMES.get(tx.get("to_account_id"), tx.get("to_account_id")),
    }
    for key in ("fee_amount", "fee_currency", "source", "purpose", "cost_basis_usd",
                "proceeds_usd", "gross_proceeds_usd", "fmv_usd", "fee_usd", "realized_gain_usd", "holding_period",
                "broker_reporting", "acquired_at"):
        val = tx.get(key)
        if val not in (None, "", "N/A") and not (key == "fee_amount" and Decimal(str(val)) == 0):
            out[key] = val
    if "proceeds_usd" not in out:  # e.g. a spend changed into a gift keeps its old gross
        out.pop("gross_proceeds_usd", None)
    if priced := _from_price(tx):
        out["from_price"] = priced
    return out


mcp = MCPServer(
    name="bitcointx",
    title="BitcoinTX",
    description="Add and correct transactions in a self-hosted BitcoinTX Bitcoin tax ledger.",
    instructions=LEDGER_GUIDE,
)
# The SDK logs at INFO to stderr, which AI apps keep in log files; httpx's
# request lines (…/price/history?date=… or ?at=…) would name the ledger's dates there.
logging.getLogger("httpx").setLevel(logging.WARNING)

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)


@mcp.tool(annotations=READ_ONLY)
@with_version_notice
def get_ledger_guide() -> str:
    """How to map exchange emails, wallet history and plain English onto BitcoinTX
    accounts, transaction types and tax fields. Read this before adding transactions."""
    return LEDGER_GUIDE


@mcp.tool(annotations=READ_ONLY)
@with_version_notice
async def get_portfolio() -> ToolResult:
    """Current balance of every account, average cost basis per BTC, the live BTC price and
    where it came from (or, when there's none, BitcoinTX's reason in btc_price_unavailable),
    and the user's tax timezone (dates without a timezone are interpreted in it).
    Useful to reconcile against what the user's cold wallet or exchange actually shows."""
    balances = await _call("GET", "/api/calculations/accounts/balances")
    avg = await _call("GET", "/api/calculations/average-cost-basis")
    unavailable = None
    try:
        price = await _call("GET", "/api/bitcoin/price")
    except ToolError as exc:
        price, unavailable = None, str(exc)  # why: Nobody, not chosen yet, no answer… (#145)
    tz = await _call("GET", "/api/settings/tax-timezone")
    return {
        "tax_timezone": tz.get("timezone"),
        "balances": [
            {"account": b["name"], "currency": b["currency"], "balance": _balance(b)}
            for b in balances
        ],
        "average_cost_basis": avg,
        "btc_price_usd": price.get("USD") if isinstance(price, dict) else None,
        "btc_price_source": price.get("source") if isinstance(price, dict) else None,
        **({"btc_price_unavailable": unavailable} if unavailable else {}),
    }


@mcp.tool(annotations=READ_ONLY)
@with_version_notice
async def list_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    type: TxTypeName | None = None,
    account: AccountName | None = None,
    limit: int = 50,
) -> ToolResult:
    """Find recorded transactions, newest first. Filter by date range (YYYY-MM-DD, inclusive,
    days in the user's tax timezone), type, and an account on either side. Use it to find an
    id before updating or deleting. A transaction with values BitcoinTX filled in from a price
    has from_price: which values, and that price's hour (or day) in UTC, source and USD per BTC."""
    first, last = _parse_filter_date(start_date), _parse_filter_date(end_date)
    zone = await _tax_zone() if first or last else timezone.utc
    start = _in_utc(first, zone, time.min) if first else None  # a date alone: the whole day
    end = _in_utc(last, zone, time.max) if last else None
    txs = await _call("GET", "/api/transactions")
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
@with_version_notice
async def get_btc_price(date: str | None = None) -> ToolResult:
    """BTC price in USD. For a transaction, pass its date and time as you would to
    add_transactions (e.g. 2025-07-31T21:05:00, in the tax timezone unless an offset is
    given): you get the price BitcoinTX itself uses for income, spending and fees, the
    price when that hour began (UTC), or that day's 00:00 UTC price where it has no hourly
    one ("moment" says which). A date alone (YYYY-MM-DD) gives that UTC day's 00:00
    price; with no date, the price right now. Use it to value income, spending, or gifts
    when the user doesn't know the USD amount. "source" says where the price came from:
    "mempool" is the user's own Mempool, any other name a public price site."""
    if date:
        data = await _call("GET", "/api/bitcoin/price/history", params=await _price_query(date))
    else:
        data = await _call("GET", "/api/bitcoin/price")
    result = {"date": date or "now", "usd": data.get("USD") if isinstance(data, dict) else data}
    if isinstance(data, dict) and data.get("moment"):
        result.update(moment=data["moment"], priced_at=data.get("at"))
    if isinstance(data, dict) and data.get("source"):
        result["source"] = data["source"]  # "mempool" (the user's own) or a public site's name (#145)
    return result


@mcp.tool(annotations=READ_ONLY)
@with_version_notice
async def review_ledger() -> ToolResult:
    """Read-only Ledger review: saved transactions worth a second look (figures Recalculate
    Ledger would change; Spent withdrawals saved with $0 proceeds; Lost withdrawals still
    carrying a loss; BTC withdrawals whose purpose isn't Spent, Gift, Donation or Lost (each
    counts as Spent until the owner chooses; only the owner knows which it was: ask, never
    guess; as Spent with none recorded, its proceeds are what the owner got for it); BTC
    deposits, not income or a rebate, with a $0 or
    blank cost basis;
    values BitcoinTX priced at the day's price that the price of their hour would change,
    by tax year, which only the owner can apply, in Settings (they change figures, and a
    year already filed is a question for a tax professional); Inherited deposits without a
    date of death; income or rebate deposits with a $0 or blank value, or with a typed value
    far from that hour's price; gifts, donations and lost coins with a $0 or blank value). Each
    item has its id, date, what looks
    odd and what would change; `total` counts these. Last, a reminder (kind "reminder", not in
    `total`, not an error): My BTC and Gift deposits without a date originally acquired,
    with one explanation for the group; pass it on in short and suggest changing the Source
    (and checking the cost basis) if they are really income, interest, rewards or rebates.
    Changes nothing; show it to the user and let them decide what to edit."""
    return await _call("GET", "/api/review")


@mcp.tool(annotations=READ_ONLY)
@with_version_notice
async def preview_transactions(transactions: list[TransactionInput]) -> ToolResult:
    """Dry run: validate transactions, auto-fill missing USD values from historical prices
    (each row's simulated.from_price says which of simulated's values and the price: its hour
    or day in UTC, source and USD per BTC; gross_proceeds_usd is before the fee),
    flag rows already in the ledger (duplicate: the same type, BTC amount, source or purpose,
    a Buy's cost basis, and minute, or day for a date alone) or like one (possible_duplicate: the same amount
    within 48 hours, the warning says what differs), and simulate the FIFO result (gain/loss,
    holding period, balances afterward). NOTHING is saved. Always call this and show the user the result
    before add_transactions. At most 500 rows a call, and fewer dated before the ledger's
    latest entry (each recalculates the whole ledger; the error says how many): split a long
    list by date, oldest first, and preview and add each part before the next."""
    return await _call("POST", "/api/import/entries/preview", json={"rows": _rows(transactions)})


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
@with_version_notice
async def add_transactions(transactions: list[TransactionInput]) -> ToolResult:
    """Save transactions to the ledger, all-or-nothing. Only call after preview_transactions and
    the user's confirmation, with the previewed rows. Each created row's from_price says which
    values came from a price and its hour, source and USD per BTC. Duplicates are skipped (keep them in the
    list: dropping one can leave an identical row beside it skipped instead), unless the user
    says one is another transaction: then send that row with not_a_duplicate true. Rows
    previewed as possible_duplicate ARE saved, so drop any the user says is already recorded.
    The same row limits as preview_transactions."""
    return await _call("POST", "/api/import/entries/execute", json={"rows": _rows(transactions)})


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
@with_version_notice
async def update_transaction(
    transaction_id: int,
    date: str | None = None,
    type: TxTypeName | None = None,
    amount: AmountValue | None = None,
    from_account: AccountName | None = None,
    to_account: AccountName | None = None,
    cost_basis_usd: UsdValue | None = None,
    proceeds_usd: UsdValue | None = None,
    fee_amount: AmountValue | None = None,
    fee_currency: Literal["BTC", "USD"] | None = None,
    source: DepositSource | None = None,
    purpose: WithdrawalPurpose | None = None,
    fmv_usd: UsdValue | None = None,
    fee_usd: UsdValue | None = None,
    broker_reporting: Literal["automatic", "none", "proceeds", "basis"] | None = None,
    acquired_at: str | None = None,
) -> ToolResult:
    """Change fields of one existing transaction (only the fields you pass). The whole ledger is
    recalculated, so gains on later sales may change. Confirm with the user first.
    date is read as add_transactions reads it: without a timezone, in the user's tax
    timezone (a bare date is midday there).
    Changing type or accounts requires passing type, from_account and to_account together.
    broker_reporting (Sell / Spent withdrawal only) records what the user's Form 1099-DA or
    1099-B actually shows for that sale, which picks the Form 8949 box: "none" (not on a
    broker form), "proceeds" (basis not reported), "basis" (basis reported), or "automatic".
    fee_usd sets a BTC fee's USD value (kept as given); without it a stored value is kept.
    An Income/Interest/Reward/Rebate deposit's value that came from the price is priced again
    (at the hour) when you change its amount, the time's hour or the account, or move it there
    from another source (a switch among those four keeps it; sending back the value it already
    has doesn't make it typed); a Spent's proceeds that came from the price, when you change
    its amount or the time's hour, or send proceeds_usd 0 (a change of purpose makes them typed);
    a Gift/Donation/Lost withdrawal's, when you change its amount or the time's hour, and a blank
    one (or a Spent's $0 made a gift without fmv_usd) is filled from the price by any change.
    A value the user typed is kept, $0 included: send fmv_usd 0 only when they mean $0.
    An Inherited deposit's is priced at its date of death (acquired_at), and again when that
    changes.
    acquired_at (MyBTC/Gift deposit) sets the date the coins were originally acquired, kept as
    that date (a date and time stands for its date in the tax timezone); "none" clears it (the
    holding period then starts at the deposit). For an Inherited deposit it is the date of
    death, which it must keep. The answer is the transaction as list_transactions shows it,
    from_price included."""
    changes: dict[str, Any] = {}
    if date is not None:
        changes["timestamp"] = await _timestamp_from(date)
    fields = (
        ("type", type),
        ("from_account_id", None if from_account is None else ACCOUNT_IDS[from_account]),
        ("to_account_id", None if to_account is None else ACCOUNT_IDS[to_account]),
        ("amount", _text(amount)),
        ("cost_basis_usd", _text(cost_basis_usd)),
        ("fee_amount", _text(fee_amount)),
        ("fmv_usd", _text(fmv_usd)),
        ("fee_usd", _text(fee_usd)),
        ("proceeds_usd", _text(proceeds_usd)),
        ("fee_currency", fee_currency),
        ("source", source),
        ("purpose", purpose),
    )
    changes.update((key, value) for key, value in fields if value is not None)
    if broker_reporting is not None:
        changes["broker_reporting"] = None if broker_reporting == "automatic" else broker_reporting
    if acquired_at is not None:
        changes["acquired_at"] = None if acquired_at.strip().lower() == "none" else await _date_from(acquired_at)
    if not changes:
        raise ToolError("No changes given.")

    await _complete_for_server_rules(transaction_id, changes, proceeds_given=proceeds_usd is not None)
    updated = await _call("PUT", f"/api/transactions/{transaction_id}", json=changes)
    return _compact(updated)


def _text(value: Decimal | None) -> str | None:
    """The number as it is written (1E-8 for a satoshi): written out, one
    far out of range such as 1E-999999 has a million digits. BitcoinTX
    reads either."""
    return None if value is None else str(value)


async def _price_query(date: str) -> dict[str, str]:
    """A date alone asks for that UTC day's price; a date and time, read as
    add_transactions reads it (the tax timezone unless an offset is given),
    for the price of its moment."""
    parsed = _parse_date_text(date.strip())
    if parsed is None:
        raise ToolError(f"Invalid date '{date}'.")
    if parsed[1]:
        return {"date": parsed[0].date().isoformat()}
    return {"at": _in_utc(parsed, await _tax_zone(), time(12)).isoformat()}


async def _timestamp_from(date: str) -> str:
    """The date as add_transactions reads it, in whole seconds."""
    parsed = _parse_date_text(date.strip())
    if parsed is None:
        raise ToolError(f"Invalid date '{date}'.")
    return _in_utc(parsed, await _tax_zone(), time(12)).replace(microsecond=0).isoformat()


async def _date_from(date: str) -> str:
    """A date originally acquired (or of death), which BitcoinTX keeps as a date (#185): a date
    alone is sent as it is, never moved by a timezone; a date and time as add_transactions
    reads it (BitcoinTX takes its date in the tax timezone)."""
    parsed = _parse_date_text(date.strip())
    if parsed is None:
        raise ToolError(f"Invalid date '{date}'.")
    return parsed[0].date().isoformat() if parsed[1] else await _timestamp_from(date)


async def _complete_for_server_rules(transaction_id: int, changes: dict[str, Any], proceeds_given: bool) -> None:
    """
    The server checks the type rules on the type and both accounts together:
    the ones not changed come from the transaction. A Sell keeps its gross
    proceeds, so recalculation doesn't subtract the USD fee again.
    """
    type_fields = ("type", "from_account_id", "to_account_id")
    changes_type = any(k in changes for k in type_fields)
    if not (proceeds_given or changes_type):
        return
    current = await _call("GET", f"/api/transactions/{transaction_id}")
    if changes_type:
        for key in type_fields:
            changes.setdefault(key, current[key])
    if proceeds_given and changes.get("type", current["type"]) == "Sell":
        changes["gross_proceeds_usd"] = changes["proceeds_usd"]


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False))
@with_version_notice
async def delete_transaction(transaction_id: int) -> ToolResult:
    """Permanently delete one transaction. The ledger is
    recalculated afterward. Confirm with the user first and tell them what you're deleting."""
    current = await _call("GET", f"/api/transactions/{transaction_id}")
    await _call("DELETE", f"/api/transactions/{transaction_id}")
    return {"deleted": _compact(current)}


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=True))
@with_version_notice
async def recalculate_ledger() -> ToolResult:
    """Rebuild all cost-basis lots, disposals and gains from the recorded transactions.
    Run it only when the user asks (after an upgrade, review_ledger shows first what it
    would change). Transactions themselves are not changed."""
    return await _call("POST", "/api/transactions/recalculate")


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False))
@with_version_notice
async def backup_ledger() -> ToolResult:
    """Save a copy of the whole BitcoinTX database next to it on the user's server (in its
    backups folder), as a safety net. Offer it before a large import or before deleting or
    changing many entries. BitcoinTX keeps the newest 3 copies (and for a week the oldest, and
    the first copy of each day it made before you changed anything that day) and makes at most
    one a minute; only the file name comes back. Restoring a copy is done by the user, not by
    you."""
    return await _call("POST", "/api/backup/ai-copy")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
