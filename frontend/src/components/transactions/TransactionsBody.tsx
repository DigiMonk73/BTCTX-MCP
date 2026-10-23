import React from "react";
import Pagination from "../Pagination";
import { ALL_ACCOUNTS, filterCount, matchesFilter, type AccountChoice } from "../../utils/accountFilter";
import { groupByDay, pageOf, sortTransactions } from "../../utils/transactionList";
import TransactionDays from "./TransactionDays";

interface TransactionsBodyProps {
  transactions: ITransaction[];
  book: AccountBook;
  accountChoice: AccountChoice;
  sortMode: SortMode;
  currentPage: number;
  pageSize: number;
  refreshing: boolean;
  onPage: (page: number) => void;
  onPageSize: (size: number) => void;
  onEdit: (id: number) => void;
}

/** The ledger's rows the account filter keeps, sorted, a page at a time. */
const TransactionsBody: React.FC<TransactionsBodyProps> = (props) => {
  const { transactions, book, accountChoice, sortMode, currentPage, pageSize, onPage } = props;
  const kept = transactions.filter((tx) => matchesFilter(tx, accountChoice, book));
  const { page, totalPages, items } = pageOf(sortTransactions(kept, sortMode), currentPage, pageSize);
  return (
    <>
      {accountChoice !== ALL_ACCOUNTS && (
        <p className="transactions-count" role="status">{filterCount(kept.length, transactions.length)}</p>
      )}

      <TransactionDays
        days={groupByDay(items)}
        book={book}
        refreshing={props.refreshing}
        noneForAccount={kept.length === 0}
        onEdit={props.onEdit}
      />

      <Pagination
        page={page}
        totalPages={totalPages}
        pageSize={pageSize}
        onPrev={() => page > 1 && onPage(page - 1)}
        onNext={() => page < totalPages && onPage(page + 1)}
        onPageSizeChange={(e) => props.onPageSize(Number(e.target.value))}
      />
    </>
  );
};

export default TransactionsBody;
