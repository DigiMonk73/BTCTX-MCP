// FILE: frontend/src/components/RiverImport.tsx
//
// River bitcoin-activity CSV import: upload → editable preview → atomic
// import. Unlike the onboarding CSV import (empty DB only), this merges
// into a live ledger; rows already in the ledger arrive pre-matched from
// the backend and are excluded from import.

import React, { useState } from "react";
import api from "../api";
import { useToast } from "../contexts/useToast";
import "../styles/riverImport.css";

interface RiverParseError {
  row_number: number;
  column?: string;
  message: string;
  severity: string;
}

interface RiverProposal {
  row_number: number;
  date: string;
  river_tag?: string;
  type: string;
  from_account: string;
  to_account: string;
  amount: string;
  cost_basis_usd?: string;
  proceeds_usd?: string;
  fee_amount?: string;
  fee_currency?: string;
  source?: string;
  purpose?: string;
  type_choices: string[];
  funding_choices: string[];
  basis_autofilled: boolean;
  status: "new" | "matched" | "discrepancy";
  matched_tx_id?: number;
  discrepancy?: string;
}

interface RiverPreviewResponse {
  success: boolean;
  total_rows: number;
  new_count: number;
  matched_count: number;
  discrepancy_count: number;
  proposals: RiverProposal[];
  errors: RiverParseError[];
  warnings: RiverParseError[];
}

interface RiverImportResponse {
  success: boolean;
  imported_count: number;
  skipped_existing: number;
  message: string;
}

/** One preview row plus the user's edits. */
interface EditableRow {
  proposal: RiverProposal;
  include: boolean;
  type: string;
  fromAccount: string;
  toAccount: string;
  costBasisUsd: string;
  feeAmount: string;
  purpose: string;
  source: string;
}

const WITHDRAWAL_PURPOSES = ["Spent", "Gift", "Donation", "Lost"];
const DEPOSIT_SOURCES = ["MyBTC", "Gift", "Income", "Interest", "Reward"];

/** Accounts implied by a type flip on a BTC move (direction-aware). */
function accountsForType(row: EditableRow, newType: string) {
  const isSend = row.proposal.from_account === "Exchange BTC";
  if (newType === "Withdrawal") return { from: "Exchange BTC", to: "External" };
  if (newType === "Deposit") return { from: "External", to: "Exchange BTC" };
  // Transfer
  return isSend
    ? { from: "Exchange BTC", to: "Wallet" }
    : { from: "Wallet", to: "Exchange BTC" };
}

function toEditableRow(p: RiverProposal): EditableRow {
  return {
    proposal: p,
    include: p.status === "new",
    type: p.type,
    fromAccount: p.from_account,
    toAccount: p.to_account,
    costBasisUsd: p.cost_basis_usd != null ? String(p.cost_basis_usd) : "",
    feeAmount: p.fee_amount != null ? String(p.fee_amount) : "",
    purpose: p.purpose ?? "Spent",
    source: p.source ?? "MyBTC",
  };
}

const STATUS_LABEL: Record<RiverProposal["status"], string> = {
  new: "New",
  matched: "In ledger",
  discrepancy: "Review",
};

const RiverImport: React.FC = () => {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<RiverPreviewResponse | null>(null);
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [showMatched, setShowMatched] = useState(false);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setRows([]);
    setShowMatched(false);
    const input = document.getElementById("river-csv-input") as HTMLInputElement;
    if (input) input.value = "";
  };

  const handlePreview = async () => {
    if (!file) return;
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      const res = await api.post<RiverPreviewResponse>("/import/river/preview", formData);
      setPreview(res.data);
      setRows(res.data.proposals.map(toEditableRow));
      setShowMatched(false);
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      toast.error(axiosErr.response?.data?.detail || "Failed to preview River CSV.");
    } finally {
      setLoading(false);
    }
  };

  const updateRow = (rowNumber: number, patch: Partial<EditableRow>) => {
    setRows((prev) =>
      prev.map((r) => (r.proposal.row_number === rowNumber ? { ...r, ...patch } : r))
    );
  };

  const handleTypeChange = (row: EditableRow, newType: string) => {
    const accounts = accountsForType(row, newType);
    updateRow(row.proposal.row_number, {
      type: newType,
      fromAccount: accounts.from,
      toAccount: accounts.to,
    });
  };

  const importableRows = rows.filter((r) => r.include && r.proposal.status !== "matched");

  const handleExecute = async () => {
    if (importableRows.length === 0) return;
    if (!window.confirm(`Import ${importableRows.length} transaction(s) from River into your ledger?`)) {
      return;
    }
    setLoading(true);
    try {
      const payload = {
        rows: importableRows.map((r) => ({
          date: r.proposal.date,
          type: r.type,
          amount: r.proposal.amount,
          from_account: r.fromAccount,
          to_account: r.toAccount,
          cost_basis_usd: r.costBasisUsd || null,
          proceeds_usd: r.proposal.proceeds_usd ?? null,
          fee_amount: r.feeAmount || null,
          fee_currency: r.feeAmount ? (r.type === "Buy" || r.type === "Sell" ? "USD" : "BTC") : null,
          source: r.type === "Deposit" ? r.source : null,
          purpose: r.type === "Withdrawal" ? r.purpose : null,
        })),
      };
      const res = await api.post<RiverImportResponse>("/import/river/execute", payload);
      toast.success(res.data.message);
      reset();
    } catch (err) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      toast.error(axiosErr.response?.data?.detail || "Import failed. No transactions were saved.");
    } finally {
      setLoading(false);
    }
  };

  const visibleRows = showMatched
    ? rows
    : rows.filter((r) => r.proposal.status !== "matched");
  const discrepancies = rows.filter((r) => r.proposal.status === "discrepancy");

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleString();
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="settings-section river-import">
      <h3>Import from River</h3>

      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">River Bitcoin Activity CSV</span>
          <p className="settings-option-subtitle">
            Download your bitcoin activity CSV from river.com → Taxes &amp; Documents,
            then upload it here. Transactions already in your ledger are detected and
            skipped — safe to re-import overlapping date ranges.
          </p>
        </div>
        <div className="river-input-row">
          <input
            type="file"
            id="river-csv-input"
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="csv-file-input"
          />
          <button
            onClick={handlePreview}
            disabled={loading || !file}
            className="settings-button"
          >
            {loading && !preview ? "Processing..." : "Preview"}
          </button>
        </div>
      </div>

      {preview && (
        <div className="river-preview">
          {/* Summary strip */}
          <div className="river-summary">
            <span className="river-chip river-chip-new">{preview.new_count} new</span>
            <span className="river-chip river-chip-matched">
              {preview.matched_count} already in ledger
            </span>
            {preview.discrepancy_count > 0 && (
              <span className="river-chip river-chip-review">
                {preview.discrepancy_count} need review
              </span>
            )}
            <span className="river-summary-total">{preview.total_rows} rows in file</span>
          </div>

          {/* Parse errors */}
          {preview.errors.length > 0 && (
            <div className="import-errors">
              <strong>Errors:</strong>
              <ul>
                {preview.errors.slice(0, 10).map((err, idx) => (
                  <li key={idx} className="import-error-item">
                    Row {err.row_number}: {err.message}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Warnings */}
          {preview.warnings.length > 0 && (
            <div className="import-warnings">
              <strong>Warnings:</strong>
              <ul>
                {preview.warnings.slice(0, 5).map((warn, idx) => (
                  <li key={idx} className="import-warning-item">
                    Row {warn.row_number}: {warn.message}
                  </li>
                ))}
                {preview.warnings.length > 5 && (
                  <li>...and {preview.warnings.length - 5} more warnings</li>
                )}
              </ul>
            </div>
          )}

          {/* Discrepancies */}
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

          {/* Editable grid */}
          {visibleRows.length > 0 && (
            <div className="import-preview-table-container river-table-container">
              <table className="import-preview-table river-table">
                <thead>
                  <tr>
                    <th className="river-col-include">Import</th>
                    <th>Status</th>
                    <th>Date</th>
                    <th>Type</th>
                    <th>From → To</th>
                    <th>Amount</th>
                    <th>Cost Basis</th>
                    <th>Proceeds</th>
                    <th>Fee</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleRows.map((row) => {
                    const p = row.proposal;
                    const isMatched = p.status === "matched";
                    return (
                      <tr key={p.row_number} className={isMatched ? "river-row-matched" : undefined}>
                        <td className="river-col-include">
                          <input
                            type="checkbox"
                            checked={row.include}
                            disabled={isMatched || loading}
                            onChange={(e) => updateRow(p.row_number, { include: e.target.checked })}
                            aria-label={`Include row ${p.row_number}`}
                          />
                        </td>
                        <td>
                          <span className={`river-status river-status-${p.status}`}>
                            {STATUS_LABEL[p.status]}
                          </span>
                        </td>
                        <td className="river-cell-date">{formatDate(p.date)}</td>
                        <td>
                          {p.type_choices.length > 1 && !isMatched ? (
                            <select
                              value={row.type}
                              disabled={loading}
                              onChange={(e) => handleTypeChange(row, e.target.value)}
                              className="river-select"
                            >
                              {p.type_choices.map((t) => (
                                <option key={t} value={t}>{t}</option>
                              ))}
                            </select>
                          ) : (
                            row.type
                          )}
                          {row.type === "Withdrawal" && p.type_choices.length > 1 && !isMatched && (
                            <select
                              value={row.purpose}
                              disabled={loading}
                              onChange={(e) => updateRow(p.row_number, { purpose: e.target.value })}
                              className="river-select river-select-secondary"
                              aria-label="Withdrawal purpose"
                            >
                              {WITHDRAWAL_PURPOSES.map((x) => (
                                <option key={x} value={x}>{x}</option>
                              ))}
                            </select>
                          )}
                          {row.type === "Deposit" && p.type_choices.length > 1 && !isMatched && (
                            <select
                              value={row.source}
                              disabled={loading}
                              onChange={(e) => updateRow(p.row_number, { source: e.target.value })}
                              className="river-select river-select-secondary"
                              aria-label="Deposit source"
                            >
                              {DEPOSIT_SOURCES.map((x) => (
                                <option key={x} value={x}>{x}</option>
                              ))}
                            </select>
                          )}
                        </td>
                        <td className="river-cell-accounts">
                          {p.funding_choices.length > 1 && !isMatched ? (
                            <span className="river-funding-toggle" role="group" aria-label="Buy funding source">
                              {p.funding_choices.map((acct) => (
                                <button
                                  key={acct}
                                  type="button"
                                  disabled={loading}
                                  className={
                                    "river-funding-option" +
                                    (row.fromAccount === acct ? " is-active" : "")
                                  }
                                  onClick={() => updateRow(p.row_number, { fromAccount: acct })}
                                >
                                  {acct}
                                </button>
                              ))}
                              <span className="river-funding-dest">→ {row.toAccount}</span>
                            </span>
                          ) : (
                            `${row.fromAccount} → ${row.toAccount}`
                          )}
                        </td>
                        <td className="river-cell-num">{p.amount} BTC</td>
                        <td className="river-cell-num">
                          {row.type === "Deposit" && !isMatched ? (
                            <span className="river-basis-edit">
                              $
                              <input
                                type="text"
                                inputMode="decimal"
                                value={row.costBasisUsd}
                                disabled={loading}
                                onChange={(e) => updateRow(p.row_number, { costBasisUsd: e.target.value })}
                                className="river-num-input"
                                aria-label="Cost basis (USD)"
                              />
                              {p.basis_autofilled && row.costBasisUsd === String(p.cost_basis_usd) && (
                                <span className="river-autofill" title="Estimated from the historical BTC price — edit if you know the exact value">
                                  est.
                                </span>
                              )}
                            </span>
                          ) : (
                            row.costBasisUsd ? `$${row.costBasisUsd}` : "—"
                          )}
                        </td>
                        <td className="river-cell-num">
                          {p.proceeds_usd ? `$${p.proceeds_usd}` : "—"}
                        </td>
                        <td className="river-cell-num">
                          {row.type === "Transfer" && !isMatched ? (
                            <input
                              type="text"
                              inputMode="decimal"
                              value={row.feeAmount}
                              disabled={loading}
                              onChange={(e) => updateRow(p.row_number, { feeAmount: e.target.value })}
                              className="river-num-input"
                              placeholder="0"
                              aria-label="Fee (BTC)"
                            />
                          ) : (
                            row.feeAmount || "—"
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {preview.matched_count > 0 && (
            <button
              type="button"
              className="river-show-matched"
              onClick={() => setShowMatched((v) => !v)}
            >
              {showMatched
                ? "Hide already-imported rows"
                : `Show ${preview.matched_count} already-imported row(s)`}
            </button>
          )}

          <div className="import-actions">
            <button
              onClick={handleExecute}
              disabled={loading || importableRows.length === 0}
              className="settings-button import-confirm"
            >
              {loading ? "Importing..." : `Import ${importableRows.length} Transaction(s)`}
            </button>
            <button onClick={reset} disabled={loading} className="settings-button">
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default RiverImport;
