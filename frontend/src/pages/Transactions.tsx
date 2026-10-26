import React, { useEffect, useRef, useState } from "react";
import { Plus } from "lucide-react";
import api from "../api";
import TransactionPanel from "../components/TransactionPanel";
import AccountFilter from "../components/transactions/AccountFilter";
import TransactionsBody from "../components/transactions/TransactionsBody";
import TransactionsStatus from "../components/transactions/TransactionsStatus";
import { ALL_ACCOUNTS, type AccountChoice } from "../utils/accountFilter";
import { parseTransaction } from "../utils/format";
import { useAccounts } from "../utils/useAccounts";
import "../styles/transactions.css";

const Transactions: React.FC = () => {
  const [isPanelOpen, setIsPanelOpen] = useState(false);
  // Where focus goes as the panel closes, when the row it edited is reloaded away (#772)
  const addButton = useRef<HTMLButtonElement>(null);
  const [transactions, setTransactions] = useState<ITransaction[] | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("TIMESTAMP_DESC");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [editingTransactionId, setEditingTransactionId] = useState<number | null>(null);

  const [currentPage, setCurrentPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [accountChoice, setAccountChoice] = useState<AccountChoice>(ALL_ACCOUNTS);
  // The names and currencies the rows show, and the filter's choices (2.0 spec 5.13)
  const { book, failed: bookFailed } = useAccounts();

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

  const handleAccountChoice = (choice: AccountChoice) => {
    setAccountChoice(choice);
    setCurrentPage(1);
  };

  const loading = isLoading || (!book && !bookFailed);

  return (
    <div className="transactions-page">
      <div className="transactions-header">
        <button ref={addButton} type="button" className="btn btn-primary" onClick={openPanel}>
          <Plus size={16} aria-hidden="true" />
          Add transaction
        </button>

        <div className="transactions-filters">
          {book && <AccountFilter book={book} value={accountChoice} onChange={handleAccountChoice} />}

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

      <TransactionsStatus
        bookFailed={bookFailed}
        loading={loading}
        fetchError={fetchError}
        empty={transactions?.length === 0}
        onRetry={fetchTransactions}
      />

      {!loading && !fetchError && book && transactions && transactions.length > 0 && (
        <TransactionsBody
          transactions={transactions}
          book={book}
          accountChoice={accountChoice}
          sortMode={sortMode}
          currentPage={currentPage}
          pageSize={pageSize}
          refreshing={isRefreshing}
          onPage={setCurrentPage}
          onPageSize={(size) => {
            setPageSize(size);
            setCurrentPage(1);
          }}
          onEdit={(id) => {
            setEditingTransactionId(id);
            setIsPanelOpen(true);
          }}
        />
      )}

      <TransactionPanel
        isOpen={isPanelOpen}
        onClose={closePanel}
        onSubmitSuccess={handleSubmitSuccess}
        transactionId={editingTransactionId}
        returnFocus={addButton}
      />
    </div>
  );
};

export default Transactions;
