import React from "react";

const ERRORS_SHOWN = 10;
const WARNINGS_SHOWN = 5;
const ROWS_SHOWN = 50;

function formatDate(dateStr: string) {
  try {
    const date = new Date(dateStr);
    return date.toLocaleString();
  } catch {
    return dateStr;
  }
}

/** A CSV import's preview: counts, errors, warnings and the first rows, with
 * the Import and Cancel buttons. */
const CsvImportPreview: React.FC<{
  preview: CSVPreviewResponse;
  loading: boolean;
  onImport: () => void;
  onCancel: () => void;
}> = ({ preview, loading, onImport, onCancel }) => (
  <div className="import-preview-container">
    <div className="import-preview-header">
      <h4>Import Preview</h4>
      <span className="import-preview-stats">
        {preview.valid_rows} valid / {preview.total_rows} total rows
        {preview.errors.length > 0 && (
          <span className="import-error-count"> | {preview.errors.length} error(s)</span>
        )}
        {preview.warnings.length > 0 && (
          <span className="import-warning-count"> | {preview.warnings.length} warning(s)</span>
        )}
      </span>
    </div>

    {preview.errors.length > 0 && (
      <div className="note note-error import-list">
        <strong>Errors (must fix before import):</strong>
        <ul>
          {preview.errors.slice(0, ERRORS_SHOWN).map((err, idx) => (
            <li key={idx} className="import-error-item">
              Row {err.row_number}{err.column ? ` (${err.column})` : ""}: {err.message}
            </li>
          ))}
          {preview.errors.length > ERRORS_SHOWN && (
            <li>...and {preview.errors.length - ERRORS_SHOWN} more errors</li>
          )}
        </ul>
      </div>
    )}

    {preview.warnings.length > 0 && (
      <div className="note note-warning import-list">
        <strong>Warnings (import will proceed):</strong>
        <ul>
          {preview.warnings.slice(0, WARNINGS_SHOWN).map((warn, idx) => (
            <li key={idx} className="import-warning-item">
              Row {warn.row_number}{warn.column ? ` (${warn.column})` : ""}: {warn.message}
            </li>
          ))}
          {preview.warnings.length > WARNINGS_SHOWN && (
            <li>...and {preview.warnings.length - WARNINGS_SHOWN} more warnings</li>
          )}
        </ul>
      </div>
    )}

    {preview.transactions.length > 0 && (
      <div className="table-scroll">
        <table className="table">
          <thead>
            <tr>
              <th>Row</th>
              <th>Date</th>
              <th>Type</th>
              <th>Amount</th>
              <th>From</th>
              <th>To</th>
              <th>Cost Basis</th>
              <th>Proceeds</th>
            </tr>
          </thead>
          <tbody>
            {preview.transactions.slice(0, ROWS_SHOWN).map((tx) => (
              <tr key={tx.row_number}>
                <td>{tx.row_number}</td>
                <td>{formatDate(tx.date)}</td>
                <td>{tx.type}</td>
                <td>{tx.amount} BTC</td>
                <td>{tx.from_account}</td>
                <td>{tx.to_account}</td>
                <td>{tx.cost_basis_usd ? `$${tx.cost_basis_usd}` : "-"}</td>
                <td>{tx.proceeds_usd ? `$${tx.proceeds_usd}` : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {preview.transactions.length > ROWS_SHOWN && (
          <p className="import-preview-more">
            ...and {preview.transactions.length - ROWS_SHOWN} more transactions
          </p>
        )}
      </div>
    )}

    <div className="import-actions">
      <button
        onClick={onImport}
        disabled={loading || !preview.can_import}
        className="btn btn-primary"
      >
        {loading ? "Importing..." : `Import ${preview.valid_rows} Transactions`}
      </button>
      <button
        onClick={onCancel}
        disabled={loading}
        className="btn btn-secondary"
      >
        Cancel
      </button>
    </div>
  </div>
);

export default CsvImportPreview;
