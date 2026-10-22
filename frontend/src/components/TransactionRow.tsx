// One row of the Transactions list: an icon for the type, a title (type and
// account) over a grey subtitle (time, source or purpose, fee), the gain for
// sells and spends (never gifts, donations or lost coins), and the amount
// that moved with its USD value under it.
import React from "react";
import { ArrowDown, ArrowLeftRight, ArrowUp, Minus, Plus, type LucideIcon } from "lucide-react";
import { accountCurrency, accountName, exchangeName, isBtcAccount } from "../utils/accounts";
import { formatBtc, formatUsd } from "../utils/format";
import { gainLabel, sourceOrPurpose } from "../utils/transactionList";

/** An account's name on the list: from the book (5.13); "N/A" for no account. */
function shownName(book: AccountBook, id: number | null): string {
  return id === null ? "N/A" : accountName(book, id);
}

function displayAccount(tx: ITransaction, book: AccountBook): string {
  const { type, from_account_id, to_account_id } = tx;
  switch (type) {
    case "Deposit":
      return shownName(book, to_account_id);
    case "Withdrawal":
      return shownName(book, from_account_id);
    case "Transfer":
      return `${shownName(book, from_account_id)} \u2192 ${shownName(book, to_account_id)}`;
    // A Buy or a Sell shows its exchange's name (5.13): the BTC account's exchange
    case "Buy":
      return to_account_id === null ? "N/A" : exchangeName(book, to_account_id);
    case "Sell":
      return from_account_id === null ? "N/A" : exchangeName(book, from_account_id);
    default:
      return "Unknown";
  }
}

function formatExtra(tx: ITransaction, book: AccountBook): string {
  const { type } = tx;
  if (type === "Deposit" || type === "Withdrawal") return sourceOrPurpose(tx);
  // A bitcoin account sent to itself records only its fee (#159): a consolidation, whichever account it is (5.5)
  const itself = type === "Transfer" && tx.from_account_id === tx.to_account_id;
  if (itself && isBtcAccount(book, tx.from_account_id ?? undefined)) {
    return "Consolidation";
  }
  return "";
}

const TYPE_ICONS: Record<string, LucideIcon> = {
  Deposit: ArrowDown,
  Withdrawal: ArrowUp,
  Transfer: ArrowLeftRight,
  Buy: Plus,
  Sell: Minus,
};

// Dollars by the account's currency, from the book (5.13)
const inDollars = (book: AccountBook, id: number | null) => accountCurrency(book, id ?? undefined) === "USD";

/** The asset that moved (signed, as the account sees it) and its USD value. */
function rowAmounts(tx: ITransaction, book: AccountBook): { primary: string; secondary: string } {
  const { type, amount, cost_basis_usd, proceeds_usd, from_account_id, to_account_id } = tx;
  const minus = "\u2212";
  switch (type) {
    case "Deposit":
      return inDollars(book, to_account_id)
        ? { primary: `+${formatUsd(amount)}`, secondary: "" }
        : { primary: `+${formatBtc(amount)}`, secondary: cost_basis_usd ? formatUsd(cost_basis_usd) : "" };
    case "Withdrawal":
      return inDollars(book, from_account_id)
        ? { primary: `${minus}${formatUsd(amount)}`, secondary: "" }
        : { primary: `${minus}${formatBtc(amount)}`, secondary: proceeds_usd ? formatUsd(proceeds_usd) : "" };
    case "Transfer":
      return { primary: inDollars(book, from_account_id) ? formatUsd(amount) : formatBtc(amount), secondary: "" };
    case "Buy":
      return { primary: `+${formatBtc(amount)}`, secondary: cost_basis_usd ? formatUsd(cost_basis_usd) : "" };
    case "Sell":
      return { primary: `${minus}${formatBtc(amount)}`, secondary: proceeds_usd ? formatUsd(proceeds_usd) : "" };
    default:
      return { primary: `${amount}`, secondary: "" };
  }
}

interface Props {
  tx: ITransaction;
  book: AccountBook;
  onEdit: (id: number) => void;
}

const TransactionRow: React.FC<Props> = ({ tx, book, onEdit }) => {
  const timeStr = new Date(tx.timestamp).toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
  let feeLabel = "";
  if (tx.fee_amount && tx.fee_amount !== 0) {
    feeLabel = tx.fee_currency === "BTC" ? `Fee ${formatBtc(tx.fee_amount)}` : `Fee ${formatUsd(tx.fee_amount)}`;
  }
  const subtitle = [timeStr, formatExtra(tx, book), feeLabel].filter(Boolean).join(" \u00b7 ");
  const gain = gainLabel(tx);
  const { primary, secondary } = rowAmounts(tx, book);
  const Icon = TYPE_ICONS[tx.type] ?? ArrowLeftRight;

  return (
    <div className="tx-row" role="listitem">
      <span className={`tx-badge tx-badge-${tx.type.toLowerCase()}`} aria-hidden="true">
        <Icon size={18} strokeWidth={2} />
      </span>
      <span className="tx-main">
        <span className="tx-title">
          {tx.type}
          <span className="tx-account">{" \u00b7 "}{displayAccount(tx, book)}</span>
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
