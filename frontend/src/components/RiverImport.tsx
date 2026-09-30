// River's bitcoin-activity CSV: upload, an editable preview, then one import
// of every ticked row. Unlike the onboarding CSV import (empty ledger only),
// this adds to a ledger in use: rows already in it come back from the server
// matched, and are left out.

import React, { useState } from "react";
import api from "../api";
import { useToast } from "../contexts/useToast";
import { detailOr } from "../utils/apiError";
import { importRow, importableRows, toEditableRow, type EditableRow } from "../utils/riverImport";
import RiverPreview from "./riverImport/RiverPreview";
import "../styles/riverImport.css";

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
      toast.error(detailOr(err, "Failed to preview River CSV."));
    } finally {
      setLoading(false);
    }
  };

  const updateRow = (rowNumber: number, patch: Partial<EditableRow>) => {
    setRows((prev) =>
      prev.map((r) => (r.proposal.row_number === rowNumber ? { ...r, ...patch } : r))
    );
  };

  const handleExecute = async () => {
    const toImport = importableRows(rows);
    if (toImport.length === 0) return;
    if (!window.confirm(`Import ${toImport.length} transaction(s) from River into your ledger?`)) {
      return;
    }
    setLoading(true);
    try {
      const res = await api.post<RiverImportResponse>("/import/river/execute", { rows: toImport.map(importRow) });
      toast.success(res.data.message);
      reset();
    } catch (err) {
      toast.error(detailOr(err, "Import failed. No transactions were saved."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-section river-import" role="region" aria-label="Import from River">
      <h3 className="section-title">Import from River</h3>

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
            aria-label="River CSV file"
            accept=".csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="csv-file-input"
          />
          <button
            onClick={handlePreview}
            disabled={loading || !file}
            className="btn btn-secondary"
          >
            {loading && !preview ? "Processing..." : "Preview"}
          </button>
        </div>
      </div>

      {preview && (
        <RiverPreview
          preview={preview}
          rows={rows}
          loading={loading}
          showMatched={showMatched}
          onToggleMatched={() => setShowMatched((v) => !v)}
          onRowChange={updateRow}
          onImport={handleExecute}
          onCancel={reset}
        />
      )}
    </div>
  );
};

export default RiverImport;
