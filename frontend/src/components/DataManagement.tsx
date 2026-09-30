import React, { useState } from "react";
import api from "../api";
import { downloadMessage } from "../utils/desktopDownload";
import CsvImportPreview from "./CsvImportPreview";

/** Clear the CSV file input. */
function clearFileInput() {
  const fileInput = document.getElementById("csv-file-input") as HTMLInputElement;
  if (fileInput) fileInput.value = "";
}

/** The server's reason for a refused request, else `fallback`. */
function detailOr(err: unknown, fallback: string): string {
  const axiosErr = err as { response?: { data?: { detail?: string } } };
  return axiosErr.response?.data?.detail || fallback;
}

/** Settings' Data Management section: delete everything, and import a CSV
 * file (the template, the instructions, a preview, the import) into an
 * empty ledger. */
const DataManagement: React.FC<SettingsSectionProps> = ({ loading, setLoading, setMessage }) => {
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState<CSVPreviewResponse | null>(null);
  const [showPreview, setShowPreview] = useState(false);

  const handleDeleteTransactions = async () => {
    if (!window.confirm("Delete ALL transactions? This cannot be undone.")) return;
    setLoading(true);
    setMessage("");

    try {
      await api.delete<ApiErrorResponse>("/transactions/delete_all");
      setMessage("All transactions deleted.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to delete transactions.");
    } finally {
      setLoading(false);
    }
  };

  /** Download a file from `path`; `what` names it in the message. */
  const download = async (path: string, filename: string, fileType: "pdf" | "csv", what: string, failed: string) => {
    setLoading(true);
    setMessage("");
    try {
      const res = await api.get(path, { responseType: "blob" });
      const outcome = await downloadMessage(new Blob([res.data]), filename, fileType, what);
      if (outcome) setMessage(outcome);
    } catch {
      setMessage(failed);
    } finally {
      setLoading(false);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    setCsvFile(e.target.files?.[0] || null);
    setCsvPreview(null);
    setShowPreview(false);
  };

  /** The database status, or null (with a message) when it can't be read. */
  const checkStatus = async (): Promise<DatabaseStatusResponse | null> => {
    try {
      const res = await api.get<DatabaseStatusResponse>("/import/status");
      return res.data;
    } catch {
      setMessage("Failed to check database status.");
      return null;
    }
  };

  const handlePreviewImport = async () => {
    if (!csvFile) {
      setMessage("Please select a CSV file first.");
      return;
    }

    setLoading(true);
    setMessage("");

    // An import needs an empty ledger: say so before previewing
    const status = await checkStatus();
    if (!status) {
      setLoading(false);
      return;
    }
    if (!status.is_empty) {
      setMessage(status.message);
      setLoading(false);
      return;
    }

    try {
      const formData = new FormData();
      formData.append("file", csvFile);
      const res = await api.post<CSVPreviewResponse>("/import/preview", formData);
      setCsvPreview(res.data);
      setShowPreview(true);
      setMessage("");
    } catch (err: unknown) {
      setMessage(detailOr(err, "Failed to preview CSV."));
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteImport = async () => {
    if (!csvFile) {
      setMessage("Please select a CSV file first.");
      return;
    }
    if (!csvPreview?.can_import) {
      setMessage("Cannot import: there are errors in the CSV file.");
      return;
    }
    if (!window.confirm(`Import ${csvPreview.valid_rows} transaction(s)? This will populate your empty database.`)) {
      return;
    }

    setLoading(true);
    setMessage("");

    try {
      const formData = new FormData();
      formData.append("file", csvFile);
      const res = await api.post("/import/execute", formData);
      setMessage(res.data.message || "Import completed successfully.");
      setCsvPreview(null);
      setShowPreview(false);
      setCsvFile(null);
      clearFileInput();
    } catch (err: unknown) {
      setMessage(detailOr(err, "Failed to import CSV."));
    } finally {
      setLoading(false);
    }
  };

  const handleCancelPreview = () => {
    setShowPreview(false);
    setCsvPreview(null);
    setCsvFile(null);
    setMessage("");
    clearFileInput();
  };

  return (
    <div className="settings-section" role="region" aria-label="Data Management">
      <h3 className="section-title">Data Management</h3>

      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">Delete All Transactions</span>
          <p className="settings-option-subtitle">
            Remove all transaction history. This action cannot be undone.
          </p>
        </div>
        <button onClick={handleDeleteTransactions} disabled={loading} className="btn btn-danger">
          {loading ? "Processing..." : "Delete"}
        </button>
      </div>

      <div className="settings-option import-section">
        <div className="option-info">
          <span className="settings-option-title">Import Transactions (CSV)</span>
          <p className="settings-option-subtitle">
            Import transactions from a CSV file. Requires an empty database.
          </p>
        </div>
        <div className="import-controls">
          <button
            onClick={() => download("/import/template", "btctx_import_template.csv", "csv", "Template",
              "Failed to download template.")}
            disabled={loading}
            className="btn btn-secondary"
          >
            {loading ? "..." : "Template"}
          </button>
          <button
            onClick={() => download("/import/instructions", "BitcoinTX_CSV_Import_Guide.pdf", "pdf", "Instructions",
              "Failed to download instructions.")}
            disabled={loading}
            className="btn btn-secondary"
          >
            {loading ? "..." : "Instructions"}
          </button>
        </div>
      </div>

      <div className="settings-option import-upload">
        <div className="option-info">
          <div className="import-input-row">
            <input
              type="file"
              id="csv-file-input"
              aria-label="CSV file to import"
              accept=".csv"
              onChange={handleFileSelect}
              className="csv-file-input"
            />
            <button
              onClick={handlePreviewImport}
              disabled={loading || !csvFile}
              className="btn btn-primary"
            >
              {loading ? "Processing..." : "Preview"}
            </button>
          </div>
        </div>
      </div>

      {showPreview && csvPreview && (
        <CsvImportPreview
          preview={csvPreview}
          loading={loading}
          onImport={handleExecuteImport}
          onCancel={handleCancelPreview}
        />
      )}

      <div className="settings-note">
        To fully reset your account, delete all transactions and update your credentials above.
      </div>
    </div>
  );
};

export default DataManagement;
