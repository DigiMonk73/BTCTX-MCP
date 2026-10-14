// The dialog before every transaction is deleted (#256): Settings' Delete
// All, and Create account on an install that has transactions. It says what
// goes, offers the encrypted backup first, and deletes only once DELETE is
// typed (the server checks it too).
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { extractErrorMessage } from "../utils/apiError";
import { CONFIRMATION, describeExtent, type LedgerExtent } from "../utils/deleteAll";
import { downloadEncryptedBackup } from "../utils/encryptedBackup";

/** Download a backup first: its password typed twice, as in Backup & Restore. */
const BackupFirst: React.FC<{ busy: boolean }> = ({ busy }) => {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const download = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") || "");
    if (password !== String(form.get("repeat") || "")) {
      setNote("The two passwords don't match.");
      return;
    }
    setSaving(true);
    try {
      setNote((await downloadEncryptedBackup(password)) ?? "");
    } catch (err) {
      setNote(extractErrorMessage(err) || "Failed to download backup.");
    } finally {
      setSaving(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className="btn btn-secondary" disabled={busy} onClick={() => setOpen(true)}>
        Download a backup first
      </button>
    );
  }
  return (
    <form onSubmit={download} className="dialog-backup">
      <input type="password" name="password" placeholder="Password" required autoComplete="new-password"
        className="input" aria-label="Encrypt with password" />
      <input type="password" name="repeat" placeholder="Repeat password" required autoComplete="new-password"
        className="input" aria-label="Repeat password" />
      <button type="submit" disabled={busy || saving} className="btn btn-secondary">
        {saving ? "Processing..." : "Download backup"}
      </button>
      {note && <p className="field-hint" role="status">{note}</p>}
    </form>
  );
};

interface DeleteAllDialogProps {
  extent: LedgerExtent;
  title: string;
  /** Logged in, the backup can be downloaded here; on Create account, the
   * owner is told how to get one. */
  canDownloadBackup: boolean;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

const DeleteAllDialog: React.FC<DeleteAllDialogProps> = ({
  extent, title, canDownloadBackup, busy, onConfirm, onCancel,
}) => {
  const [typed, setTyped] = useState("");
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && !busy && onCancel();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onCancel]);
  const noun = extent.transactions === 1 ? "transaction" : "transactions";

  return (
    <div className="dialog-backdrop">
      <div className="dialog card" role="dialog" aria-modal="true"
        aria-labelledby="delete-all-title" aria-describedby="delete-all-what">
        <h3 id="delete-all-title" className="card-title">{title}</h3>
        <p id="delete-all-what">
          This deletes {describeExtent(extent)}: every transaction, and the tax figures made from them.
          It can't be undone here.
        </p>
        <p className="dialog-note">
          BitcoinTX first keeps a copy of the database in its data folder (in <code>backups</code>,
          unencrypted), to help put it back.
        </p>
        <div className="dialog-section">
          <p className="dialog-note">A backup of your own, encrypted, that Restore can bring back:</p>
          {canDownloadBackup ? (
            <BackupFirst busy={busy} />
          ) : (
            <p className="dialog-note">
              <Link to="/login">Log in</Link> with your current login, then Settings → Backup &amp; Restore →
              Download Encrypted Backup.
            </p>
          )}
        </div>
        <div className="field">
          <label htmlFor="delete-all-confirm" className="field-label">
            Type {CONFIRMATION} to confirm
          </label>
          <input id="delete-all-confirm" className="input" value={typed} autoComplete="off" spellCheck={false}
            autoFocus onChange={(e) => setTyped(e.target.value)} disabled={busy} />
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>Cancel</button>
          <button type="button" className="btn btn-danger" onClick={onConfirm}
            disabled={busy || typed !== CONFIRMATION}>
            {busy ? "Deleting..." : `Delete ${extent.transactions} ${noun}`}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeleteAllDialog;
