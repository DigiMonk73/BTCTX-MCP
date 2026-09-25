import React, { useEffect, useState } from "react";
import TransactionPanel from "../components/TransactionPanel";
import "../styles/transactions.css";
import api from "../api";
import {
  parseTransaction,
  formatUsd,
  formatBtc,
  parseDecimal,
  formatTimestamp,
} from "../utils/format";

void formatTimestamp;
void parseDecimal;

/* Utility Functions (unchanged) */

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
      return `${accountIdToName(from_account_id)} -> ${accountIdToName(to_account_id)}`;
    case "Buy":
    case "Sell":
      return "Exchange";
    default:
      return "Unknown";
  }
}

function formatAmount(tx: ITransaction): string {
  const { type, amount, cost_basis_usd, proceeds_usd, from_account_id, to_account_id } = tx;
  switch (type) {
    case "Deposit":
      if (to_account_id === 1 || to_account_id === 3) return formatUsd(amount);
      return formatBtc(amount);
    case "Withdrawal":
      if (from_account_id === 1 || from_account_id === 3) return formatUsd(amount);
      return formatBtc(amount);
    case "Transfer":
      if (from_account_id === 1 || from_account_id === 3) return formatUsd(amount);
      return formatBtc(amount);
    case "Buy":
      return cost_basis_usd
        ? `${formatUsd(cost_basis_usd)} -> ${formatBtc(amount)}`
        : `${formatUsd(amount)}`;
    case "Sell":
      return proceeds_usd
        ? `${formatBtc(amount)} -> ${formatUsd(proceeds_usd)}`
        : `${formatBtc(amount)}`;
    default:
      return `${amount}`;
  }
}

function formatExtra(tx: ITransaction): string {
  const { type, source, purpose } = tx;
  if (type === "Deposit" && source && source !== "N/A") return source;
  if (type === "Withdrawal" && purpose && purpose !== "N/A") return purpose;
  return "";
}

function buildDisposalLabel(tx: ITransaction): string {
  if (tx.type !== "Sell" && tx.type !== "Withdrawal") return "";
  if (tx.cost_basis_usd == null || tx.realized_gain_usd == null) return "";

  const costBasis = parseDecimal(tx.cost_basis_usd);
  const gainVal = parseDecimal(tx.realized_gain_usd);
  const hp = tx.holding_period ? ` (${tx.holding_period})` : "";
  const label = gainVal >= 0 ? "Gain" : "Loss";

  if (costBasis === 0) {
    if (gainVal === 0) return "";
    const sign = gainVal >= 0 ? "+" : "-";
    return `${label}: ${sign}${formatUsd(Math.abs(gainVal))}${hp}`;
  }
  const gainPerc = (gainVal / costBasis) * 100;
  const sign = gainVal >= 0 ? "+" : "-";
  const absGain = Math.abs(gainVal);
  const absPerc = Math.abs(gainPerc).toFixed(2);

  return `${label}: ${sign}${formatUsd(absGain)} (${sign}${absPerc}%)${hp}`;
}

/* --------------------------------------------------------------------------
   MAIN COMPONENT
------------------------------------------------------------------------- */
const Transactions: React.FC = () => {
  // Panel & data states
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [transactions, setTransactions] = useState<ITransaction[] | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("TIMESTAMP_DESC");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [editingTransactionId, setEditingTransactionId] = useState<number | null>(null);

  // Pagination states
  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10); // default 10, user can change it

  // --------------------------------------------------
  // Fetch Transactions
  // --------------------------------------------------
  const fetchTransactions = async () => {
    setIsLoading(true);
    setFetchError(null);
    try {
      const res = await api.get<ITransactionRaw[]>("/transactions");
      const parsed = res.data.map(raw => parseTransaction(raw));
      setTransactions(parsed);
    } catch (err) {
      const errorMsg =
        err instanceof Error
          ? `Failed to load transactions: ${err.message}`
          : "Failed to load transactions: Unknown error";
      setFetchError(errorMsg);
      setTransactions(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchTransactions();
  }, []);

  // --------------------------------------------------
  // Dialog Toggles
  // --------------------------------------------------
  const openPanel = () => setIsPanelOpen(true);
  const closePanel = () => {
    setIsPanelOpen(false);
    setEditingTransactionId(null);
  };

  const handleSubmitSuccess = async () => {
    setIsPanelOpen(false);
    setEditingTransactionId(null);
    setIsRefreshing(true);
    try {
      await fetchTransactions();
    } finally {
      setIsRefreshing(false);
    }
  };

  // --------------------------------------------------
  // Sorting
  // --------------------------------------------------
  const sortedTransactions = transactions
    ? [...transactions].sort((a, b) => {
        if (sortMode === "TIMESTAMP_DESC") {
          return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
        } else {
          // CREATION_DESC => sort by ID descending
          return b.id - a.id;
        }
      })
    : [];

  // --------------------------------------------------
  // Pagination
  // --------------------------------------------------
  const totalTransactions = sortedTransactions.length;
  const totalPages = Math.ceil(totalTransactions / pageSize);

  // clamp currentPage to [1, totalPages]
  const page = Math.min(Math.max(currentPage, 1), totalPages || 1);

  const startIndex = (page - 1) * pageSize;
  const endIndex = startIndex + pageSize;
  const transactionsForPage = sortedTransactions.slice(startIndex, endIndex);

  // group by date for only the current page
  const groupedByDate: Record<string, ITransaction[]> = {};
  for (const tx of transactionsForPage) {
    const dateLabel = new Date(tx.timestamp).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    if (!groupedByDate[dateLabel]) groupedByDate[dateLabel] = [];
    groupedByDate[dateLabel].push(tx);
  }
  const dateGroups = Object.entries(groupedByDate);

  const handlePrevPage = () => {
    if (page > 1) setCurrentPage(page - 1);
  };
  const handleNextPage = () => {
    if (page < totalPages) setCurrentPage(page + 1);
  };

  // If the user changes page size, reset to page 1
  const handlePageSizeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setPageSize(Number(e.target.value));
    setCurrentPage(1); // Reset pagination
  };

  // --------------------------------------------------
  // Render
  // --------------------------------------------------
  return (
    <div className="transactions-page">
      {/* Header row with Add button (left) and sort dropdown (right) */}
      <div className="transactions-header">
        <button className="add-transaction-btn" onClick={openPanel}>
          Add Transaction
        </button>

        <div className="sort-wrapper">
          <select
            className="sort-select"
            aria-label="Sort transactions"
            value={sortMode}
            onChange={e => setSortMode(e.target.value as SortMode)}
          >
            <option value="TIMESTAMP_DESC">Sort by Date</option>
            <option value="CREATION_DESC">Last Added (ID)</option>
          </select>
        </div>
      </div>

      {isLoading && <p>Loading transactions...</p>}
      {fetchError && (
        <div className="error-section">
          <p>{fetchError}</p>
          <button onClick={fetchTransactions} className="retry-btn">
            Retry
          </button>
        </div>
      )}

      {!isLoading && !fetchError && transactions && transactions.length === 0 && (
        <p>No transactions found.</p>
      )}

      {!isLoading && !fetchError && transactions && transactions.length > 0 && (
        <>
          <div className="transactions-list">
            {isRefreshing && (
              <div className="refreshing-container">
                <div className="spinner"></div>
                <p>Refreshing transactions...</p>
              </div>
            )}

            {dateGroups.map(([dayLabel, txArray]) => (
              <div key={dayLabel} className="transactions-day-group">
                <h3 className="date-heading">{dayLabel}</h3>
                {txArray.map(tx => {
                  const timeStr = new Date(tx.timestamp).toLocaleTimeString("en-US", {
                    hour: "numeric",
                    minute: "2-digit",
                  });

                  const accountLabel = resolveDisplayAccount(tx);
                  const amountLabel = formatAmount(tx);

                  let feeLabel = "";
                  if (tx.fee_amount && tx.fee_amount !== 0) {
                    feeLabel =
                      tx.fee_currency === "BTC"
                        ? `Fee: ${formatBtc(tx.fee_amount)}`
                        : `Fee: ${formatUsd(tx.fee_amount)} ${tx.fee_currency || "USD"}`;
                  }

                  const extraLabel = formatExtra(tx);
                  const disposalLabel = buildDisposalLabel(tx);
                  const disposalColor = tx.realized_gain_usd >= 0 ? "gain-green" : "loss-red";

                  return (
                    <div key={tx.id} className="transaction-card">
                      <span className="cell time-col">{timeStr}</span>
                      <span className="cell type-col">{tx.type}</span>
                      <span className="cell account-col">{accountLabel}</span>
                      <span className="cell amount-col">{amountLabel}</span>
                      <span className="cell fee-col">{feeLabel}</span>
                      <span className="cell extra-col">{extraLabel}</span>
                      <span className={`cell disposal-col ${disposalColor}`}>
                        {disposalLabel}
                      </span>
                      <button
                        onClick={() => {
                          setEditingTransactionId(tx.id);
                          setIsPanelOpen(true);
                        }}
                        className="edit-button"
                      >
                        Edit
                      </button>
                    </div>
                  );
                })}
              </div>
            ))}
          </div>

          {/* Pagination controls */}
          <div className="pagination-wrapper">
            <div className="pagination-container">
              <button
                className="pagination-button"
                onClick={handlePrevPage}
                disabled={page <= 1}
              >
                « Prev
              </button>

              <span className="pagination-info">
                Page {page} of {totalPages}
              </span>

              <button
                className="pagination-button"
                onClick={handleNextPage}
                disabled={page >= totalPages}
              >
                Next »
              </button>
            </div>

            {/* Items per page dropdown */}
            <div className="page-size-container">
              <label htmlFor="pageSize" className="page-size-label">
                Items per page:
              </label>
              <select
                id="pageSize"
                value={pageSize}
                onChange={handlePageSizeChange}
                className="page-size-select"
              >
                <option value="10">10</option>
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
            </div>
          </div>
        </>
      )}

      {/* TransactionPanel for adding/editing */}
      <TransactionPanel
        isOpen={isPanelOpen}
        onClose={closePanel}
        onSubmitSuccess={handleSubmitSuccess}
        transactionId={editingTransactionId}
      />
    </div>
  );
};

export default Transactions;
