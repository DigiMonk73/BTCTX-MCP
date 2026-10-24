// River's bitcoin-activity CSV: upload, an editable preview, then one import
// of every ticked row. Unlike the onboarding CSV import (empty ledger only),
// this adds to a ledger in use: rows already in it come back from the server
// matched, and are left out unless the owner ticks them (#253).

import React, { useEffect, useState } from "react";
import api from "../api";
import { useToast } from "../contexts/useToast";
import { detailOr } from "../utils/apiError";
import { importNote } from "../utils/pastYears";
import {
  importRequestRows, importableRows, refusedCellPlace, toEditableRow, type EditableRow,
} from "../utils/riverImport";
import PastYearDialog from "./PastYearDialog";
import RiverPreview from "./riverImport/RiverPreview";
import { usePastYearWarning } from "./transactionForm/usePastYearWarning";
import "../styles/riverImport.css";

/** `onPreviewShown(true)` while a preview is open: its table needs the
 * window's width, wider than the Settings card (#259). */
const RiverImport: React.FC<{ onPreviewShown: (shown: boolean) => void }> = ({ onPreviewShown }) => {
  const toast = useToast();
  const pastYears = usePastYearWarning();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<RiverPreviewResponse | null>(null);
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [showMatched, setShowMatched] = useState(false);
  useEffect(() => onPreviewShown(preview !== null), [preview, onPreviewShown]);

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
    const sent = importRequestRows(rows);
    setLoading(true);
    try {
      // Rows that change an earlier tax year are imported only once the owner confirms it (2.0 spec 5.8)
      const res = await pastYears.attempt("import", (confirm) =>
        api.post<RiverImportResponse>("/import/river/execute", { rows: sent }, confirm ? { params: { confirm } } : undefined));
      if (res === null) return; // cancelled: nothing imported, the preview stays as it was
      toast.success(res.data.message);
      reset();
    } catch (err) {
      toast.error(detailOr(err, "Import failed. No transactions were saved.", refusedCellPlace(sent)));
    } finally {
      setLoading(false);
    }
  };

  const pastYearsNote = preview && importNote(preview.past_years_dated);

  return (
    <div className="settings-section river-import" role="region" aria-label="Import from River">
      <h3 className="section-title">Import from River</h3>

      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">River Bitcoin Activity CSV</span>
          <p className="settings-option-subtitle">
            Download your bitcoin activity CSV from river.com → Taxes &amp; Documents,
            then upload it here. Transactions already in your ledger are found and
            left out, so overlapping date ranges can be imported again.
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

      {pastYearsNote && <p className="note" role="note">{pastYearsNote}</p>}

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
      {pastYears.question && <PastYearDialog {...pastYears.question} />}
    </div>
  );
};

export default RiverImport;
