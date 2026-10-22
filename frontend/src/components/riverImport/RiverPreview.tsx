import React from "react";
import { problemText } from "../../utils/importProblem";
import { importableRows, type EditableRow } from "../../utils/riverImport";
import RiverRow from "./RiverRow";

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
  // A row already in the ledger shows when asked for, or once ticked: never
  // imported out of sight (#253)
  const visibleRows = showMatched
    ? rows
    : rows.filter((r) => r.proposal.status !== "matched" || r.include);
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

      {/* Every error and warning, each list scrolling when long: a row
          they name may be left out of the import, so none is hidden (#455) */}
      {preview.errors.length > 0 && (
        <div className="note note-error import-list river-problems">
          <strong>Errors ({preview.errors.length}):</strong>
          <ul tabIndex={0} aria-label="Errors">
            {preview.errors.map((err, idx) => (
              <li key={idx} className="import-error-item">
                {problemText(err)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {preview.warnings.length > 0 && (
        <div className="note note-warning import-list river-problems">
          <strong>Warnings ({preview.warnings.length}):</strong>
          <ul tabIndex={0} aria-label="Warnings">
            {preview.warnings.map((warn, idx) => (
              <li key={idx} className="import-warning-item">
                {problemText(warn)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {discrepancies.length > 0 && (
        <div className="river-discrepancies">
          <strong>Possible matches with your ledger</strong>
          <p className="river-discrepancy-hint">
            These look like transactions you already recorded, but something
            differs. Those of the same amount are ticked, so they&apos;re
            imported: untick one if it&apos;s the one already in your ledger. Those
            of a different amount are left out: tick one if it&apos;s another
            transaction.
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
      {showMatched && preview.matched_count > 0 && (
        <p className="river-discrepancy-hint">
          Rows already in your ledger (the same kind, amount and minute) are left
          out. Tick one to import it anyway, if it&apos;s another transaction.
        </p>
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
