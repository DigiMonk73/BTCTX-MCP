import React from "react";
import api from "../api";
import { downloadMessage } from "../utils/desktopDownload";

/** Settings' Backup & Restore section: the CSV export, the encrypted backup
 * and its restore. */
const BackupRestore: React.FC<SettingsSectionProps> = ({ loading, setLoading, setMessage }) => {
  const handleExportCsv = async () => {
    setLoading(true);
    setMessage("");

    try {
      const res = await api.get("/backup/csv", { responseType: "blob" });
      const date = new Date().toISOString().split("T")[0];
      const outcome = await downloadMessage(new Blob([res.data]), `btctx_transactions_${date}.csv`, "csv", "CSV export");
      if (outcome) setMessage(outcome);
    } catch {
      setMessage("Failed to export CSV.");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadBackup = async (event: React.FormEvent<HTMLFormElement>) => {
    // The password is typed twice in hidden fields: a typo in a password
    // shown as typed made a backup no one could open.
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") || "");
    if (password !== String(form.get("repeat") || "")) {
      setMessage("The two passwords don't match.");
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
      const outcome = await downloadMessage(new Blob([res.data]), "bitcoin_backup.btx", "btx", "Backup");
      if (outcome) setMessage(outcome);
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
      // The restored database may have other user ids: log in again (the
      // login in use stays; the backup's doesn't come back).
      setTimeout(() => {
        window.location.href = "/login";
      }, 2000);
    } catch {
      setMessage("Failed to restore backup.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="settings-section" role="region" aria-label="Backup & Restore">
      <h3 className="section-title">Backup & Restore</h3>
      <p className="settings-option-subtitle">
        BitcoinTX also keeps a few unencrypted safety copies of its database in its data folder,
        next to the database: from before updates and restores, and those an AI assistant makes.
      </p>

      <div className="settings-option">
        <div className="option-info">
          <span className="settings-option-title">Export as CSV</span>
          <p className="settings-option-subtitle">
            Export all transactions as a CSV file (unencrypted, editable).
          </p>
        </div>
        <button onClick={handleExportCsv} disabled={loading} className="btn btn-secondary">
          {loading ? "Processing..." : "Export CSV"}
        </button>
      </div>

      <div className="settings-option">
        <form onSubmit={handleDownloadBackup} className="option-info">
          <span className="settings-option-title">Download Encrypted Backup</span>
          <p className="settings-option-subtitle">
            Save a secure backup of all app data (encrypted SQLite file). Keep the password:
            without it the backup can't be opened.
          </p>
          <div className="restore-input-row">
            <input type="password" name="password" placeholder="Password" required autoComplete="new-password"
              className="input" aria-label="Encrypt with password" />
            <input type="password" name="repeat" placeholder="Repeat password" required autoComplete="new-password"
              className="input" aria-label="Repeat password" />
            <button type="submit" disabled={loading} className="btn btn-primary">
              {loading ? "Processing..." : "Download"}
            </button>
          </div>
        </form>
      </div>

      <div className="settings-option">
        <form onSubmit={handleRestoreBackup} className="option-info" encType="multipart/form-data">
          <span className="settings-option-title">Restore from Backup</span>
          <p className="settings-option-subtitle">
            Upload a previously saved backup file and enter your password.
          </p>
          <div className="restore-input-row">
            <input type="file" name="file" accept=".btx" required aria-label="Backup file" />
            <input type="password" name="password" placeholder="Password" required className="input" aria-label="Backup password" />
            <button type="submit" disabled={loading} className="btn btn-secondary">
              {loading ? "Processing..." : "Restore"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default BackupRestore;
