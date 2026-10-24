import React from "react";
import { ACCOUNTS_FAILED } from "../../utils/useAccounts";

interface TransactionsStatusProps {
  /** The account book wouldn't load: the rows can't name their accounts */
  bookFailed: boolean;
  loading: boolean;
  fetchError: string | null;
  /** The ledger has no transactions at all */
  empty: boolean;
  onRetry: () => void;
}

/** What the page shows in place of its rows: loading, an error, or an empty ledger. */
const TransactionsStatus: React.FC<TransactionsStatusProps> = ({ bookFailed, loading, fetchError, empty, onRetry }) => {
  if (bookFailed) {
    return (
      <div className="transactions-list transactions-status" role="alert">
        <p className="note note-error">{ACCOUNTS_FAILED}</p>
      </div>
    );
  }
  if (fetchError) {
    return (
      <div className="transactions-list transactions-status" role="alert">
        <p className="note note-error">{fetchError}</p>
        <button type="button" onClick={onRetry} className="btn btn-secondary">
          Retry
        </button>
      </div>
    );
  }
  if (loading) {
    return (
      <div className="transactions-list">
        <div className="loading-row transactions-status">
          <div className="spinner" /> Loading transactions…
        </div>
      </div>
    );
  }
  if (!empty) return null;
  return (
    <div className="transactions-list empty-state">
      <p>No transactions found.</p>
      <p className="field-hint">Add one above, or import a River or CSV file in Settings.</p>
    </div>
  );
};

export default TransactionsStatus;
