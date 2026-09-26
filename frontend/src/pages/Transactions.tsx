import React, { useEffect, useState } from "react";
import { ArrowDown, ArrowLeftRight, ArrowUp, Minus, Plus, type LucideIcon } from "lucide-react";
import TransactionPanel from "../components/TransactionPanel";
import "../styles/transactions.css";
import api from "../api";
import {
  parseTransaction,
  formatUsd,
  formatSignedUsd,
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
              <div key={dayLabel} className="transactions-day-group" role="list" aria-label={dayLabel}>
                <h3 className="date-heading">{dayLabel}</h3>
                {txArray.map(tx => {
                  const timeStr = new Date(tx.timestamp).toLocaleTimeString("en-US", {
                    hour: "numeric",
                    minute: "2-digit",
                  });

                  const accountLabel = resolveDisplayAccount(tx);

                  let feeLabel = "";
                  if (tx.fee_amount && tx.fee_amount !== 0) {
                    feeLabel =
                      tx.fee_currency === "BTC"
                        ? `Fee ${formatBtc(tx.fee_amount)}`
                        : `Fee ${formatUsd(tx.fee_amount)}`;
                  }

                  const extraLabel = formatExtra(tx);
                  const gain = gainLabel(tx);
                  const gainColor = tx.realized_gain_usd >= 0 ? "gain-green" : "loss-red";
                  const { primary, secondary } = rowAmounts(tx);
                  const Icon = TYPE_ICONS[tx.type] ?? ArrowLeftRight;
                  const subtitle = [timeStr, extraLabel, feeLabel].filter(Boolean).join(" \u00b7 ");

                  return (
                    <div key={tx.id} className="transaction-card tx-row" role="listitem">
                      <span className={`tx-badge tx-badge-${tx.type.toLowerCase()}`} aria-hidden="true">
                        <Icon size={18} strokeWidth={2} />
                      </span>
                      <span className="tx-main">
                        <span className="tx-title">
                          {tx.type}
                          <span className="tx-account">{" \u00b7 "}{accountLabel}</span>
                        </span>
                        <span className="tx-sub">{subtitle}</span>
                      </span>
                      <span className={`tx-gain ${gainColor}`}>{gain}</span>
                      <span className="tx-amounts">
                        <span className="tx-primary">{primary}</span>
                        {secondary && <span className="tx-secondary">{secondary}</span>}
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
