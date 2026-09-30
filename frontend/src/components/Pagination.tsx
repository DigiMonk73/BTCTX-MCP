import React from "react";

interface PaginationProps {
  page: number;
  totalPages: number;
  pageSize: number;
  onPrev: () => void;
  onNext: () => void;
  onPageSizeChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
}

/** The Transactions list's page buttons and its items-per-page choice. */
const Pagination: React.FC<PaginationProps> = ({ page, totalPages, pageSize, onPrev, onNext, onPageSizeChange }) => (
  <div className="pagination">
    <div className="pagination-pages">
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={onPrev}
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
        onClick={onNext}
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
        onChange={onPageSizeChange}
        className="input input-sm"
      >
        <option value="10">10</option>
        <option value="25">25</option>
        <option value="50">50</option>
        <option value="100">100</option>
      </select>
    </div>
  </div>
);

export default Pagination;
