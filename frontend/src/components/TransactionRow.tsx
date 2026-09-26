// One row of the Transactions list: an icon for the type, a title (type and
// account) over a grey subtitle (time, source or purpose, fee), the gain for
// sells and spends, and the amount that moved with its USD value under it.
import React from "react";
import { ArrowDown, ArrowLeftRight, ArrowUp, Minus, Plus, type LucideIcon } from "lucide-react";
import { formatBtc, formatSignedUsd, formatUsd, parseDecimal } from "../utils/format";

function accountIdToName(id: number | null): string {
  if (id === null) return "N/A";
  switch (id) {
    case 1:
      return "Bank";
    case 2:
      return "Wallet";
    case 3:
    case 4:
      return "Exchange";
    case 99:
      return "External";
    default:
      return `Acct #${id}`;
  }
}

function resolveDisplayAccount(tx: ITransaction): string {
  const { type, from_account_id, to_account_id } = tx;
  switch (type) {
    case "Deposit":
      return accountIdToName(to_account_id);
    case "Withdrawal":
      return accountIdToName(from_account_id);
    case "Transfer":
      return `${accountIdToName(from_account_id)} \u2192 ${accountIdToName(to_account_id)}`;
    case "Buy":
    case "Sell":
      return "Exchange";
    default:
      return "Unknown";
  }
}

function formatExtra(tx: ITransaction): string {
  const { type, source, purpose } = tx;
  if (type === "Deposit" && source && source !== "N/A") return source;
  if (type === "Withdrawal" && purpose && purpose !== "N/A") return purpose;
  return "";
}

const TYPE_ICONS: Record<string, LucideIcon> = {
  Deposit: ArrowDown,
  Withdrawal: ArrowUp,
  Transfer: ArrowLeftRight,
  Buy: Plus,
  Sell: Minus,
};

const isUsdAccount = (id: number | null) => id === 1 || id === 3;

/** The asset that moved (signed, as the account sees it) and its USD value. */
function rowAmounts(tx: ITransaction): { primary: string; secondary: string } {
  const { type, amount, cost_basis_usd, proceeds_usd, from_account_id, to_account_id } = tx;
  const minus = "\u2212";
  switch (type) {
    case "Deposit":
      return isUsdAccount(to_account_id)
        ? { primary: `+${formatUsd(amount)}`, secondary: "" }
        : { primary: `+${formatBtc(amount)}`, secondary: cost_basis_usd ? formatUsd(cost_basis_usd) : "" };
    case "Withdrawal":
      return isUsdAccount(from_account_id)
        ? { primary: `${minus}${formatUsd(amount)}`, secondary: "" }
        : { primary: `${minus}${formatBtc(amount)}`, secondary: proceeds_usd ? formatUsd(proceeds_usd) : "" };
    case "Transfer":
      return { primary: isUsdAccount(from_account_id) ? formatUsd(amount) : formatBtc(amount), secondary: "" };
    case "Buy":
      return { primary: `+${formatBtc(amount)}`, secondary: cost_basis_usd ? formatUsd(cost_basis_usd) : "" };
    case "Sell":
      return { primary: `${minus}${formatBtc(amount)}`, secondary: proceeds_usd ? formatUsd(proceeds_usd) : "" };
    default:
      return { primary: `${amount}`, secondary: "" };
  }
}

function gainLabel(tx: ITransaction): string {
  if (tx.type !== "Sell" && tx.type !== "Withdrawal") return "";
  if (tx.cost_basis_usd == null || tx.realized_gain_usd == null) return "";
  const gain = parseDecimal(tx.realized_gain_usd);
  const basis = parseDecimal(tx.cost_basis_usd);
  if (gain === 0 && basis === 0) return "";
  const term = tx.holding_period === "LONG" ? "Long-term" : tx.holding_period === "SHORT" ? "Short-term" : "";
  const pct = basis !== 0 ? `${gain >= 0 ? "+" : "\u2212"}${Math.abs((gain / basis) * 100).toFixed(2)}%` : "";
  return [`${gain >= 0 ? "Gain" : "Loss"} ${formatSignedUsd(gain)}`, pct, term].filter(Boolean).join(" \u00b7 ");
}

interface Props {
  tx: ITransaction;
  onEdit: (id: number) => void;
}

const TransactionRow: React.FC<Props> = ({ tx, onEdit }) => {
  const timeStr = new Date(tx.timestamp).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
  let feeLabel = "";
  if (tx.fee_amount && tx.fee_amount !== 0) {
    feeLabel = tx.fee_currency === "BTC" ? `Fee ${formatBtc(tx.fee_amount)}` : `Fee ${formatUsd(tx.fee_amount)}`;
  }
  const subtitle = [timeStr, formatExtra(tx), feeLabel].filter(Boolean).join(" \u00b7 ");
  const gain = gainLabel(tx);
  const { primary, secondary } = rowAmounts(tx);
  const Icon = TYPE_ICONS[tx.type] ?? ArrowLeftRight;

  return (
    <div className="tx-row" role="listitem">
      <span className={`tx-badge tx-badge-${tx.type.toLowerCase()}`} aria-hidden="true">
        <Icon size={18} strokeWidth={2} />
      </span>
      <span className="tx-main">
        <span className="tx-title">
          {tx.type}
          <span className="tx-account">{" \u00b7 "}{resolveDisplayAccount(tx)}</span>
        </span>
        <span className="tx-sub">{subtitle}</span>
      </span>
      <span className={`tx-gain ${tx.realized_gain_usd >= 0 ? "text-gain" : "text-loss"}`}>{gain}</span>
      <span className="tx-amounts">
        <span className="tx-primary">{primary}</span>
        {secondary && <span className="tx-secondary">{secondary}</span>}
      </span>
      <button type="button" onClick={() => onEdit(tx.id)} className="btn btn-quiet btn-sm tx-edit">
        Edit
      </button>
    </div>
  );
};

export default TransactionRow;
