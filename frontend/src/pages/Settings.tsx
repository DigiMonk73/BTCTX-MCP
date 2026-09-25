// FILE: frontend/src/pages/Settings.tsx

import React, { useState } from "react";
import api from "../api";
import ConnectAiSetting from "../components/ConnectAiSetting";
import RiverImport from "../components/RiverImport";
import TaxTimezoneSetting from "../components/TaxTimezoneSetting";
import { downloadFile, isDesktopApp } from "../utils/desktopDownload";
import "../styles/settings.css";

// ApiErrorResponse is defined in types/global.d.ts

interface CSVRowPreview {
  row_number: number;
  date: string;
  type: string;
  amount: string;
  from_account: string;
  to_account: string;
  cost_basis_usd?: string;
  proceeds_usd?: string;
  fee_amount?: string;
  fee_currency?: string;
  source?: string;
  purpose?: string;
  notes?: string;
}

interface CSVParseError {
  row_number: number;
  column?: string;
  message: string;
  severity: string;
}

interface CSVPreviewResponse {
  success: boolean;
  total_rows: number;
  valid_rows: number;
  transactions: CSVRowPreview[];
  errors: CSVParseError[];
  warnings: CSVParseError[];
  can_import: boolean;
}

interface DatabaseStatusResponse {
  is_empty: boolean;
  transaction_count: number;
  message: string;
}

const Settings: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");

  // CSV Import state
  const [csvFile, setCsvFile] = useState<File | null>(null);
  const [csvPreview, setCsvPreview] = useState<CSVPreviewResponse | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [, setDbStatus] = useState<DatabaseStatusResponse | null>(null);

  // Reused for most actions
  const getUserId = async (): Promise<number | null> => {
    try {
      const res = await api.get("/users/");
      const users = res.data as { id: number; username: string }[];
      return users.length > 0 ? users[0].id : null;
    } catch {
      return null;
    }
  };

  const logoutAndRedirect = async () => {
    try {
      await api.post("/logout", {}, { withCredentials: true });
      window.location.href = "/login";
    } catch {
      setMessage("Failed to log out. Please try again.");
    }
  };

  const handleLogout = async () => {
    if (!window.confirm("Are you sure you want to log out?")) return;
    setLoading(true);
    setMessage("");
    await logoutAndRedirect();
    setLoading(false);
  };

  // ✳️ Credential update logic (username/password)
  const handleCredentialUpdate = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setMessage("");

    if (
      !window.confirm(
        "This will reset your username and password, but keep existing transactions.\n\nContinue?"
      )
    ) {
      setLoading(false);
      return;
    }

    try {
      const userId = await getUserId();
      if (!userId) {
        setMessage("No user found to reset credentials.");
        return;
      }

      if (!newUsername && !newPassword) {
        setMessage("Please enter a new username or password (or both).");
        return;
      }

      await api.patch(`/users/${userId}`, {
        username: newUsername || undefined,
        password: newPassword || undefined,
      });

      setMessage("Credentials updated successfully.");
      setNewUsername("");
      setNewPassword("");
    } catch {
      setMessage("Failed to reset credentials.");
    } finally {
      setLoading(false);
    }
  };

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

  const handleDownloadBackup = async () => {
    const password = prompt("Enter a password to encrypt the backup:");
    if (!password) {
      setMessage("Backup canceled.");
      return;
    }

    setLoading(true);
    setMessage("");

    try {
      const formData = new FormData();
      formData.append("password", password);

      const res = await api.post("/backup/download", formData, {
        responseType: "blob",
      });

      const blob = new Blob([res.data]);
      const result = await downloadFile(blob, "bitcoin_backup.btx", "btx");

      if (result.success) {
        if (isDesktopApp() && result.path) {
          setMessage(`Backup saved to: ${result.path}`);
        } else {
          setMessage("Backup downloaded.");
        }
      } else if (result.error && result.error !== "Save cancelled") {
        setMessage(`Save failed: ${result.error}`);
      }
    } catch {
      setMessage("Failed to download backup.");
    } finally {
      setLoading(false);
    }
  };

  const handleRestoreBackup = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setMessage("");

    const formData = new FormData(event.currentTarget);
    const password = formData.get("password");
    const file = formData.get("file");

    if (!password || !(file instanceof File)) {
      setMessage("Please provide both a password and a file.");
      setLoading(false);
      return;
    }

    try {
      formData.set("file", file);
      const res = await api.post("/backup/restore", formData);
      setMessage(res.data.message || "Backup restored. Redirecting to login...");
      // After restore, the session may be invalid (different user_id in restored DB)
      // Redirect to login so user can authenticate with restored credentials
      setTimeout(() => {
        window.location.href = "/login";
      }, 2000);
    } catch {
      setMessage("Failed to restore backup.");
    } finally {
      setLoading(false);
    }
  };

  // CSV Import handlers
  const handleDownloadTemplate = async () => {
    setLoading(true);
    setMessage("");

    try {
      const res = await api.get("/import/template", { responseType: "blob" });
      const blob = new Blob([res.data]);
      const result = await downloadFile(blob, "btctx_import_template.csv", "csv");

      if (result.success) {
        if (isDesktopApp() && result.path) {
          setMessage(`Template saved to: ${result.path}`);
        } else {
          setMessage("Template downloaded.");
        }
      } else if (result.error && result.error !== "Save cancelled") {
        setMessage(`Save failed: ${result.error}`);
      }
    } catch {
      setMessage("Failed to download template.");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadInstructions = async () => {
    setLoading(true);
    setMessage("");

    try {
      const res = await api.get("/import/instructions", { responseType: "blob" });
      const blob = new Blob([res.data]);
      const result = await downloadFile(blob, "BitcoinTX_CSV_Import_Guide.pdf", "pdf");

      if (result.success) {
        if (isDesktopApp() && result.path) {
          setMessage(`Instructions saved to: ${result.path}`);
        } else {
          setMessage("Instructions downloaded.");
        }
      } else if (result.error && result.error !== "Save cancelled") {
        setMessage(`Save failed: ${result.error}`);
      }
    } catch {
      setMessage("Failed to download instructions.");
    } finally {
      setLoading(false);
    }
  };

  const handleRecalculate = async () => {
    setLoading(true);
    setMessage("");
    try {
      const res = await api.post<{ detail: string }>("/transactions/recalculate");
      setMessage(res.data.detail);
    } catch {
      setMessage("Recalculation failed. Your data was not changed.");
    } finally {
      setLoading(false);
    }
  };

  const handleExportCsv = async () => {
    setLoading(true);
    setMessage("");

    try {
      const res = await api.get("/backup/csv", { responseType: "blob" });
      const blob = new Blob([res.data]);
      const date = new Date().toISOString().split("T")[0];
      const filename = `btctx_transactions_${date}.csv`;
      const result = await downloadFile(blob, filename, "csv");

      if (result.success) {
        if (isDesktopApp() && result.path) {
          setMessage(`CSV export saved to: ${result.path}`);
        } else {
          setMessage("CSV export downloaded.");
        }
      } else if (result.error && result.error !== "Save cancelled") {
        setMessage(`Save failed: ${result.error}`);
      }
    } catch {
      setMessage("Failed to export CSV.");
    } finally {
      setLoading(false);
    }
  };

  const handleCheckStatus = async () => {
    try {
      const res = await api.get<DatabaseStatusResponse>("/import/status");
      setDbStatus(res.data);
      return res.data;
    } catch {
      setMessage("Failed to check database status.");
      return null;
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setCsvFile(file);
    setCsvPreview(null);
    setShowPreview(false);
    setDbStatus(null);
  };

  const handlePreviewImport = async () => {
    if (!csvFile) {
      setMessage("Please select a CSV file first.");
      return;
    }

    setLoading(true);
    setMessage("");

    // Check status first
    const status = await handleCheckStatus();
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
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setMessage(axiosErr.response?.data?.detail || "Failed to preview CSV.");
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
      // Reset file input
      const fileInput = document.getElementById("csv-file-input") as HTMLInputElement;
      if (fileInput) fileInput.value = "";
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setMessage(axiosErr.response?.data?.detail || "Failed to import CSV.");
    } finally {
      setLoading(false);
    }
  };

  const handleCancelPreview = () => {
    setShowPreview(false);
    setCsvPreview(null);
    setCsvFile(null);
    setDbStatus(null);
    setMessage("");
    const fileInput = document.getElementById("csv-file-input") as HTMLInputElement;
    if (fileInput) fileInput.value = "";
  };

  const formatDate = (dateStr: string) => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="settings-container">
      <h2 className="settings-title">Settings</h2>

      {/* ✅ Account Section */}
      <div className="settings-section">
        <h3>Account</h3>

        {/* Logout */}
        <div className="settings-option">
          <div className="option-info">
            <span className="settings-option-title">Logout</span>
            <p className="settings-option-subtitle">Sign out of your account.</p>
          </div>
          <button onClick={handleLogout} disabled={loading} className="settings-button">
            {loading ? "Processing..." : "Logout"}
          </button>
        </div>

        {/* Reset Username & Password */}
        <div className="settings-option">
          <div className="option-info">
            <span className="settings-option-title">Reset Username &amp; Password</span>
            <p className="settings-option-subtitle">
              Change your username and password without deleting any transactions.
            </p>
          </div>

          <form onSubmit={handleCredentialUpdate} className="credential-update-form">
            <div className="credential-inputs">
              <input
                type="text"
                placeholder="New Username"
                aria-label="New username"
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                className="credential-input"
              />
              <input
                type="password"
                placeholder="New Password"
                aria-label="New password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                className="credential-input"
              />
            </div>

            <div className="credential-submit-container">
              <button type="submit" className="settings-button" disabled={loading}>
                {loading ? "Processing..." : "Update"}
              </button>
            </div>
          </form>
        </div>

        <TaxTimezoneSetting />

        <div className="settings-option">
          <div className="option-info">
            <span className="settings-option-title">Recalculate Ledger</span>
            <p className="settings-option-subtitle">
              Rebuild all lots, balances and gains from your transactions. Run once after
              upgrading BitcoinTX so calculation fixes apply to existing data.
            </p>
          </div>
          <button onClick={handleRecalculate} disabled={loading} className="settings-button">
            {loading ? "Processing..." : "Recalculate"}
          </button>
        </div>
      </div>

      {/* ✅ Connect an AI Assistant (MCP) */}
      <ConnectAiSetting />

      {/* ✅ Data Management */}
      <div className="settings-section">
        <h3>Data Management</h3>

        <div className="settings-option">
          <div className="option-info">
            <span className="settings-option-title">Delete All Transactions</span>
            <p className="settings-option-subtitle">
              Remove all transaction history. This action cannot be undone.
            </p>
          </div>
          <button onClick={handleDeleteTransactions} disabled={loading} className="settings-button danger">
            {loading ? "Processing..." : "Delete"}
          </button>
        </div>

        {/* CSV Import */}
        <div className="settings-option import-section">
          <div className="option-info">
            <span className="settings-option-title">Import Transactions (CSV)</span>
            <p className="settings-option-subtitle">
              Import transactions from a CSV file. Requires an empty database.
            </p>
          </div>
          <div className="import-controls">
            <button onClick={handleDownloadTemplate} disabled={loading} className="settings-button">
              {loading ? "..." : "Template"}
            </button>
            <button onClick={handleDownloadInstructions} disabled={loading} className="settings-button">
              {loading ? "..." : "Instructions"}
            </button>
          </div>
        </div>

        {/* CSV File Upload */}
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
                className="settings-button"
              >
                {loading ? "Processing..." : "Preview"}
              </button>
            </div>
          </div>
        </div>

        {/* CSV Preview Table */}
        {showPreview && csvPreview && (
          <div className="import-preview-container">
            <div className="import-preview-header">
              <h4>Import Preview</h4>
              <span className="import-preview-stats">
                {csvPreview.valid_rows} valid / {csvPreview.total_rows} total rows
                {csvPreview.errors.length > 0 && (
                  <span className="import-error-count"> | {csvPreview.errors.length} error(s)</span>
                )}
                {csvPreview.warnings.length > 0 && (
                  <span className="import-warning-count"> | {csvPreview.warnings.length} warning(s)</span>
                )}
              </span>
            </div>

            {/* Errors */}
            {csvPreview.errors.length > 0 && (
              <div className="import-errors">
                <strong>Errors (must fix before import):</strong>
                <ul>
                  {csvPreview.errors.slice(0, 10).map((err, idx) => (
                    <li key={idx} className="import-error-item">
                      Row {err.row_number}{err.column ? ` (${err.column})` : ""}: {err.message}
                    </li>
                  ))}
                  {csvPreview.errors.length > 10 && (
                    <li>...and {csvPreview.errors.length - 10} more errors</li>
                  )}
                </ul>
              </div>
            )}

            {/* Warnings */}
            {csvPreview.warnings.length > 0 && (
              <div className="import-warnings">
                <strong>Warnings (import will proceed):</strong>
                <ul>
                  {csvPreview.warnings.slice(0, 5).map((warn, idx) => (
                    <li key={idx} className="import-warning-item">
                      Row {warn.row_number}{warn.column ? ` (${warn.column})` : ""}: {warn.message}
                    </li>
                  ))}
                  {csvPreview.warnings.length > 5 && (
                    <li>...and {csvPreview.warnings.length - 5} more warnings</li>
                  )}
                </ul>
              </div>
            )}

            {/* Preview Table */}
            {csvPreview.transactions.length > 0 && (
              <div className="import-preview-table-container">
                <table className="import-preview-table">
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
                    {csvPreview.transactions.slice(0, 50).map((tx) => (
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
                {csvPreview.transactions.length > 50 && (
                  <p className="import-preview-more">
                    ...and {csvPreview.transactions.length - 50} more transactions
                  </p>
                )}
              </div>
            )}

            {/* Action Buttons */}
            <div className="import-actions">
              <button
                onClick={handleExecuteImport}
                disabled={loading || !csvPreview.can_import}
                className="settings-button import-confirm"
              >
                {loading ? "Importing..." : `Import ${csvPreview.valid_rows} Transactions`}
              </button>
              <button
                onClick={handleCancelPreview}
                disabled={loading}
                className="settings-button"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* ✳️ Reset Account Removed */}
        <div className="settings-note">
          To fully reset your account, delete all transactions and update your credentials above.
        </div>
      </div>

      {/* ✅ River Import */}
      <RiverImport />

      {/* ✅ Backup & Restore */}
      <div className="settings-section">
        <h3>Backup & Restore</h3>

        <div className="settings-option">
          <div className="option-info">
            <span className="settings-option-title">Export as CSV</span>
            <p className="settings-option-subtitle">
              Export all transactions as a CSV file (unencrypted, editable).
            </p>
          </div>
          <button onClick={handleExportCsv} disabled={loading} className="settings-button">
            {loading ? "Processing..." : "Export CSV"}
          </button>
        </div>

        <div className="settings-option">
          <div className="option-info">
            <span className="settings-option-title">Download Encrypted Backup</span>
            <p className="settings-option-subtitle">
              Save a secure backup of all app data (encrypted SQLite file).
            </p>
          </div>
          <button onClick={handleDownloadBackup} disabled={loading} className="settings-button">
            {loading ? "Processing..." : "Download"}
          </button>
        </div>

        <div className="settings-option">
          <form onSubmit={handleRestoreBackup} className="option-info" encType="multipart/form-data">
            <span className="settings-option-title">Restore from Backup</span>
            <p className="settings-option-subtitle">
              Upload a previously saved backup file and enter your password.
            </p>
            <div className="restore-input-row">
              <input type="file" name="file" accept=".btx" required aria-label="Backup file" />
              <input type="password" name="password" placeholder="Password" required className="credential-input" aria-label="Backup password" />
              <button type="submit" disabled={loading} className="settings-button">
                {loading ? "Processing..." : "Restore"}
              </button>
            </div>
          </form>
        </div>
      </div>

      {message && <p className="settings-message">{message}</p>}
    </div>
  );
};

export default Settings;
