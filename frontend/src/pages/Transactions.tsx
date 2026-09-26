import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import TransactionPanel from "../components/TransactionPanel";
import TransactionRow from "../components/TransactionRow";
import "../styles/transactions.css";
import api from "../api";
import { parseTransaction } from "../utils/format";

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
      <div className="transactions-header">
        <button type="button" className="btn btn-primary" onClick={openPanel}>
          <Plus size={16} aria-hidden="true" />
          Add transaction
        </button>

        <select
          className="input select-pill"
          aria-label="Sort transactions"
          value={sortMode}
          onChange={e => setSortMode(e.target.value as SortMode)}
        >
          <option value="TIMESTAMP_DESC">Sort by date</option>
          <option value="CREATION_DESC">Last added</option>
        </select>
      </div>

      {isLoading && (
        <div className="transactions-list">
          <div className="loading-row transactions-status">
            <div className="spinner" /> Loading transactions…
          </div>
        </div>
      )}
      {fetchError && (
        <div className="transactions-list transactions-status" role="alert">
          <p className="note note-error">{fetchError}</p>
          <button type="button" onClick={fetchTransactions} className="btn btn-secondary">
            Retry
          </button>
        </div>
      )}

      {!isLoading && !fetchError && transactions && transactions.length === 0 && (
        <div className="transactions-list empty-state">
          <p>No transactions found.</p>
          <p className="field-hint">Add one above, or import a River or CSV file in Settings.</p>
        </div>
      )}

      {!isLoading && !fetchError && transactions && transactions.length > 0 && (
        <>
          <div className="transactions-list" aria-busy={isRefreshing}>
            {isRefreshing && (
              <div className="loading-row transactions-status">
                <div className="spinner" /> Refreshing transactions…
              </div>
            )}

            {dateGroups.map(([dayLabel, txArray]) => (
              <div key={dayLabel} className="transactions-day-group" role="list" aria-label={dayLabel}>
                <h3 className="date-heading">{dayLabel}</h3>
                {txArray.map(tx => (
                  <TransactionRow
                    key={tx.id}
                    tx={tx}
                    onEdit={id => {
                      setEditingTransactionId(id);
                      setIsPanelOpen(true);
                    }}
                  />
                ))}
              </div>
            ))}
          </div>

          <div className="pagination">
            <div className="pagination-pages">
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handlePrevPage}
                disabled={page <= 1}
              >
                « Prev
              </button>
              <span className="pagination-info">
                Page {page} of {totalPages}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleNextPage}
                disabled={page >= totalPages}
              >
                Next »
              </button>
            </div>

            <div className="pagination-size">
              <label htmlFor="pageSize">Items per page</label>
              <select
                id="pageSize"
                value={pageSize}
                onChange={handlePageSizeChange}
                className="input input-sm"
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
