import React from "react";
import { importableRows, type EditableRow } from "../../utils/riverImport";
import RiverRow from "./RiverRow";

const ERRORS_SHOWN = 10;
const WARNINGS_SHOWN = 5;

interface RiverPreviewProps {
  preview: RiverPreviewResponse;
  rows: EditableRow[];
  loading: boolean;
  showMatched: boolean;
  onToggleMatched: () => void;
  onRowChange: (rowNumber: number, patch: Partial<EditableRow>) => void;
  onImport: () => void;
  onCancel: () => void;
}

/** A River file's preview: counts, problems, possible mismatches with the
 * ledger and the rows to review, with the Import and Cancel buttons. */
const RiverPreview: React.FC<RiverPreviewProps> = ({
  preview, rows, loading, showMatched, onToggleMatched, onRowChange, onImport, onCancel,
}) => {
  const visibleRows = showMatched
    ? rows
    : rows.filter((r) => r.proposal.status !== "matched");
  const discrepancies = rows.filter((r) => r.proposal.status === "discrepancy");
  const importCount = importableRows(rows).length;

  return (
    <div className="river-preview">
      <div className="river-summary">
        <span className="badge badge-accent">{preview.new_count} new</span>
        <span className="badge">
          {preview.matched_count} already in ledger
        </span>
        {preview.discrepancy_count > 0 && (
          <span className="badge badge-warning">
            {preview.discrepancy_count} need review
          </span>
        )}
        <span className="river-summary-total">{preview.total_rows} rows in file</span>
      </div>

      {preview.errors.length > 0 && (
        <div className="note note-error import-list">
          <strong>Errors:</strong>
          <ul>
            {preview.errors.slice(0, ERRORS_SHOWN).map((err, idx) => (
              <li key={idx} className="import-error-item">
                Row {err.row_number}: {err.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {preview.warnings.length > 0 && (
        <div className="note note-warning import-list">
          <strong>Warnings:</strong>
          <ul>
            {preview.warnings.slice(0, WARNINGS_SHOWN).map((warn, idx) => (
              <li key={idx} className="import-warning-item">
                Row {warn.row_number}: {warn.message}
              </li>
            ))}
            {preview.warnings.length > WARNINGS_SHOWN && (
              <li>...and {preview.warnings.length - WARNINGS_SHOWN} more warnings</li>
            )}
          </ul>
        </div>
      )}

      {discrepancies.length > 0 && (
        <div className="river-discrepancies">
          <strong>Possible mismatches with your ledger</strong>
          <p className="river-discrepancy-hint">
            These look like events you already recorded, but the details differ.
            They are excluded by default — tick a row's Import box only if it is
            genuinely missing from your ledger.
          </p>
          <ul>
            {discrepancies.map((r) => (
              <li key={r.proposal.row_number} className="river-discrepancy-item">
                Row {r.proposal.row_number}: {r.proposal.discrepancy}
              </li>
            ))}
          </ul>
        </div>
      )}

      {visibleRows.length > 0 && (
        <div className="table-scroll river-table-container">
          <table className="table river-table">
            <thead>
              <tr>
                <th className="river-col-include">Import</th>
                <th>Status</th>
                <th>Date</th>
                <th>Type</th>
                <th>From → To</th>
                <th>Amount</th>
                <th>Cost Basis</th>
                <th>Proceeds (before fee)</th>
                <th>Fee</th>
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => (
                <RiverRow
                  key={row.proposal.row_number}
                  row={row}
                  loading={loading}
                  onChange={(patch) => onRowChange(row.proposal.row_number, patch)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {preview.matched_count > 0 && (
        <button
          type="button"
          className="link river-show-matched"
          onClick={onToggleMatched}
        >
          {showMatched
            ? "Hide already-imported rows"
            : `Show ${preview.matched_count} already-imported row(s)`}
        </button>
      )}

      <div className="import-actions">
        <button
          onClick={onImport}
          disabled={loading || importCount === 0}
          className="btn btn-primary"
        >
          {loading ? "Importing..." : `Import ${importCount} Transaction(s)`}
        </button>
        <button onClick={onCancel} disabled={loading} className="btn btn-secondary">
          Cancel
        </button>
      </div>
    </div>
  );
};

export default RiverPreview;
