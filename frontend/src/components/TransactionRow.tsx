// One row of the Transactions list: an icon for the type, a title (type and
// account) over a grey subtitle (time, source or purpose, fee), the gain for
// sells and spends (never gifts, donations or lost coins), and the amount
// that moved with its USD value under it.
import React from "react";
import { ArrowDown, ArrowLeftRight, ArrowUp, Minus, Plus, type LucideIcon } from "lucide-react";
import { formatBtc, formatUsd } from "../utils/format";
import { gainLabel } from "../utils/transactionList";
import { rowAccounts, rowAmounts, rowNote } from "../utils/transactionRows";

const TYPE_ICONS: Record<string, LucideIcon> = {
  Deposit: ArrowDown,
  Withdrawal: ArrowUp,
  Transfer: ArrowLeftRight,
  Buy: Plus,
  Sell: Minus,
};

interface Props {
  tx: ITransaction;
  /** The account book, for the row's names and currencies (2.0 spec 5.13) */
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
  const subtitle = [timeStr, rowNote(tx, book), feeLabel].filter(Boolean).join(" \u00b7 ");
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
          <span className="tx-account">{" \u00b7 "}{rowAccounts(tx, book)}</span>
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
