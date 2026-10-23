import React, { useRef, useState } from "react";
import api from "../api";
import { detailOr, extractErrorMessage } from "../utils/apiError";
import { CONFIRMATION, describeExtent, extentToConfirm, type LedgerExtent } from "../utils/deleteAll";
import { downloadMessage } from "../utils/desktopDownload";
import CsvImportPreview from "./CsvImportPreview";
import DeleteAllDialog from "./DeleteAllDialog";

function clearFileInput() {
  const fileInput = document.getElementById("csv-file-input") as HTMLInputElement;
  if (fileInput) fileInput.value = "";
}

/** Settings' Data Management section: delete everything, and import a CSV
 * file (the template, the instructions, a preview, the import) into an
 * empty ledger. */
const DataManagement: React.FC<SettingsSectionProps> = ({ loading, setLoading, setMessage }) => {
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState<CSVPreviewResponse | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  // What Delete All would take, while its dialog is open (#256)
  const [toDelete, setToDelete] = useState<LedgerExtent | null>(null);
  // The ledger changed after the owner confirmed: the dialog shows what goes now (#377)
  const [ledgerChanged, setLedgerChanged] = useState(false);
  const deleteButton = useRef<HTMLButtonElement>(null);

  const handleDeleteTransactions = async () => {
    setLoading(true);
    setMessage("");
    try {
      const { data } = await api.get<LedgerExtent>("/transactions/delete_all");
      setLedgerChanged(false);
      if (data.transactions === 0) setMessage("There are no transactions to delete.");
      else setToDelete(data);
    } catch (error) {
      setMessage(extractErrorMessage(error) || "Couldn't read the ledger.");
    } finally {
      setLoading(false);
    }
  };

  /** Deletes what the dialog shows, sent along: the server refuses a
   * ledger that changed since (#377), and the dialog then shows what goes now. */
  const confirmDelete = async () => {
    if (!toDelete) return;
    setLoading(true);
    try {
      await api.delete("/transactions/delete_all", { params: { confirm: CONFIRMATION, ...toDelete } });
      setMessage(
        `Deleted ${describeExtent(toDelete)}. A copy of the database from before is kept in ` +
          "BitcoinTX's data folder (in backups, unencrypted).",
      );
      setToDelete(null);
    } catch (error) {
      const now = extentToConfirm(error);
      if (now && now.transactions > 0) {
        setLedgerChanged(true);
        setToDelete(now);
      } else {
        setMessage(extractErrorMessage(error) || "Failed to delete transactions.");
        setToDelete(null);
      }
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
    <>

      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">Delete All Transactions</span>
          <p className="settings-option-subtitle">
            Remove all transaction history, for example to import a corrected CSV file. It asks
            first, and keeps a copy of the database in the data folder before it deletes.
          </p>
        </div>
        <button ref={deleteButton} onClick={handleDeleteTransactions} disabled={loading} className="btn btn-danger">
          {loading ? "Processing..." : "Delete"}
        </button>
      </div>
      {toDelete && (
        <DeleteAllDialog
          extent={toDelete}
          changed={ledgerChanged}
          title="Delete all transactions?"
          canDownloadBackup
          busy={loading}
          opener={deleteButton}
          onConfirm={confirmDelete}
          onCancel={() => setToDelete(null)}
        />
      )}

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
    </>
  );
};

export default DataManagement;
