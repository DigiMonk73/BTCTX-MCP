// The dialog before every transaction is deleted (#256): Settings' Delete
// All, and Create account on an install that has transactions. It says what
// goes, offers the encrypted backup first, and deletes only once DELETE is
// typed (the server checks it too).
import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { CONFIRMATION, describeExtent, type LedgerExtent } from "../utils/deleteAll";
import { keepFocusIn } from "../utils/dialogFocus";
import BackupFirst from "./BackupFirst";

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
  // A backup downloading: nothing is deleted or closed until it's saved
  const [saving, setSaving] = useState(false);
  const waiting = busy || saving;
  const dialog = useRef<HTMLDivElement>(null);
  // Focus goes back to what opened the dialog when it closes
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    return () => opener?.focus();
  }, []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !waiting) onCancel();
      keepFocusIn(dialog.current, e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [waiting, onCancel]);
  const noun = extent.transactions === 1 ? "transaction" : "transactions";

  return (
    <div className="dialog-backdrop">
      <div ref={dialog} className="dialog card" role="dialog" aria-modal="true"
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
            <BackupFirst busy={busy} onSaving={setSaving} />
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
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={waiting}>Cancel</button>
          <button type="button" className="btn btn-danger" onClick={onConfirm}
            disabled={waiting || typed !== CONFIRMATION}>
            {busy ? "Deleting..." : `Delete ${extent.transactions} ${noun}`}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DeleteAllDialog;
