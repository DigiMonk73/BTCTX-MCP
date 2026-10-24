import React from "react";
import TransactionRow from "../TransactionRow";

interface TransactionDaysProps {
  days: [string, ITransaction[]][];
  book: AccountBook;
  refreshing: boolean;
  /** The account filter left nothing of a ledger that has rows */
  noneForAccount: boolean;
  onEdit: (id: number) => void;
}

/** The page's rows under their day headings. */
const TransactionDays: React.FC<TransactionDaysProps> = ({ days, book, refreshing, noneForAccount, onEdit }) => (
  <div className="transactions-list" aria-busy={refreshing}>
    {refreshing && (
      <div className="loading-row transactions-status">
        <div className="spinner" /> Refreshing transactions…
      </div>
    )}

    {noneForAccount && (
      <div className="empty-state">
        <p>No transactions for this account.</p>
      </div>
    )}

    {days.map(([dayLabel, txArray]) => (
      <div key={dayLabel} className="transactions-day-group" role="list" aria-label={dayLabel}>
        <h3 className="date-heading">{dayLabel}</h3>
        {txArray.map((tx) => (
          <TransactionRow key={tx.id} tx={tx} book={book} onEdit={onEdit} />
        ))}
      </div>
    ))}
  </div>
);

export default TransactionDays;
