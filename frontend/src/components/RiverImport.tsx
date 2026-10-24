// River's bitcoin-activity CSV: upload, an editable preview, then one import
// of every ticked row. Unlike the onboarding CSV import (empty ledger only),
// this adds to a ledger in use: rows already in it come back from the server
// matched, and are left out unless the owner ticks them (#253).

import React, { useEffect, useState } from "react";
import api from "../api";
import { useToast } from "../contexts/useToast";
import { detailOr } from "../utils/apiError";
import {
  chosenRiverAccounts, importRequestRows, importableRows, refusedCellPlace, riverAccountNames, riverChoices,
  toEditableRow, type EditableRow, type RiverPick,
} from "../utils/riverImport";
import RiverAccountPickers from "./riverImport/RiverAccountPickers";
import RiverPreview from "./riverImport/RiverPreview";
import "../styles/riverImport.css";

interface RiverImportProps {
  /** `onPreviewShown(true)` while a preview is open: its table needs the
   * window's width, wider than the Settings card (#259). */
  onPreviewShown: (shown: boolean) => void;
  /** Your accounts, for the file's exchange and wallet; undefined until read. */
  book?: AccountBook;
}

const RiverImport: React.FC<RiverImportProps> = ({ onPreviewShown, book }) => {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [preview, setPreview] = useState<RiverPreviewResponse | null>(null);
  const [rows, setRows] = useState<EditableRow[]>([]);
  const [showMatched, setShowMatched] = useState(false);
  const [picked, setPicked] = useState<RiverPick>({});
  useEffect(() => onPreviewShown(preview !== null), [preview, onPreviewShown]);

  // The file's exchange and wallet (5.11, 5.13)
  const choices = book ? riverChoices(book) : undefined;
  const chosen = chosenRiverAccounts(choices, picked);
  const unchosen = choices !== undefined && (chosen.exchange === undefined || chosen.wallet === undefined);

  const reset = () => {
    setFile(null);
    setPreview(null);
    setRows([]);
    setShowMatched(false);
    const input = document.getElementById("river-csv-input") as HTMLInputElement;
    if (input) input.value = "";
  };

  const handlePreview = async (pick: RiverPick = chosen) => {
    if (!file) return;
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append("file", file);
      // Before the book is read none is sent, and the server takes your first exchange and wallet
      if (pick.exchange !== undefined) formData.append("exchange_account_id", String(pick.exchange));
      if (pick.wallet !== undefined) formData.append("wallet_account_id", String(pick.wallet));
      const res = await api.post<RiverPreviewResponse>("/import/river/preview", formData);
      const accounts = riverAccountNames(book, pick);
      setPreview(res.data);
      setRows(res.data.proposals.map((p) => toEditableRow(p, accounts)));
      setShowMatched(false);
    } catch (err) {
      toast.error(detailOr(err, "Failed to preview River CSV."));
    } finally {
      setLoading(false);
    }
  };

  // A new pick makes a new preview: the rows' accounts and what's already in the ledger follow it
  const choose = (pick: RiverPick) => {
    setPicked(pick);
    if (preview) void handlePreview(pick);
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
      const res = await api.post<RiverImportResponse>("/import/river/execute", { rows: sent });
      toast.success(res.data.message);
      reset();
    } catch (err) {
      toast.error(detailOr(err, "Import failed. No transactions were saved.", refusedCellPlace(sent)));
    } finally {
      setLoading(false);
    }
  };

  return (
    <>

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
            onClick={() => void handlePreview()}
            disabled={loading || !file || unchosen}
            className="btn btn-secondary"
          >
            {loading && !preview ? "Processing..." : "Preview"}
          </button>
        </div>
      </div>

      {choices && <RiverAccountPickers choices={choices} chosen={chosen} disabled={loading} onChange={choose} />}

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
    </>
  );
};

export default RiverImport;
