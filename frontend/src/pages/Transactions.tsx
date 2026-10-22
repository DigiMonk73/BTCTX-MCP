import React, { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import api from "../api";
import Pagination from "../components/Pagination";
import TransactionPanel from "../components/TransactionPanel";
import TransactionRow from "../components/TransactionRow";
import { parseTransaction } from "../utils/format";
import { accountName, chosenId, yours } from "../utils/accounts";
import { byAccount, groupByDay, pageOf, sortTransactions } from "../utils/transactionList";
import { ACCOUNTS_FAILED, useAccounts } from "../utils/useAccounts";
import "../styles/transactions.css";

const Transactions: React.FC = () => {
  const { book, failed } = useAccounts();
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  const [transactions, setTransactions] = useState<ITransaction[] | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("TIMESTAMP_DESC");
  // The filter select's value: "" for every account (chosenId reads it)
  const [accountFilter, setAccountFilter] = useState("");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [editingTransactionId, setEditingTransactionId] = useState<number | null>(null);

  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);

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

  const sorted = transactions ? sortTransactions(byAccount(transactions, chosenId(accountFilter)), sortMode) : [];
  const { page, totalPages, items: transactionsForPage } = pageOf(sorted, currentPage, pageSize);
  const dateGroups = groupByDay(transactionsForPage);

  const handlePrevPage = () => {
    if (page > 1) setCurrentPage(page - 1);
  };
  const handleNextPage = () => {
    if (page < totalPages) setCurrentPage(page + 1);
  };

  const handleAccountFilterChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setAccountFilter(e.target.value);
    setCurrentPage(1);
  };

  const handlePageSizeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setPageSize(Number(e.target.value));
    setCurrentPage(1);
  };

  // Every row's names come from the book (5.13): the page waits for it
  if (failed) {
    return (
      <div className="transactions-page">
        <div className="transactions-list transactions-status" role="alert">
          <p className="note note-error">{ACCOUNTS_FAILED}</p>
        </div>
      </div>
    );
  }
  if (!book) {
    return (
      <div className="transactions-page">
        <div className="transactions-list">
          <div className="loading-row transactions-status">
            <div className="spinner" /> Loading transactions…
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="transactions-page">
      <div className="transactions-header">
        <button type="button" className="btn btn-primary" onClick={openPanel}>
          <Plus size={16} aria-hidden="true" />
          Add transaction
        </button>

        <div className="transactions-filters">
          <select
            className="input select-pill"
            aria-label="Filter by wallet, exchange or bank"
            value={accountFilter}
            onChange={handleAccountFilterChange}
          >
            <option value="">All accounts</option>
            {/* Hidden accounts too: old rows name them (5.5) */}
            {yours(book).map(id => (
              <option key={id} value={id}>
                {accountName(book, id)}
              </option>
            ))}
          </select>
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
                    book={book}
                    onEdit={id => {
                      setEditingTransactionId(id);
                      setIsPanelOpen(true);
                    }}
                  />
                ))}
              </div>
            ))}
          </div>

          <Pagination
            page={page}
            totalPages={totalPages}
            pageSize={pageSize}
            onPrev={handlePrevPage}
            onNext={handleNextPage}
            onPageSizeChange={handlePageSizeChange}
          />
        </>
      )}

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
