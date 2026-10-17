// "Download a backup first", in the dialog before every transaction is
// deleted (#256): the encrypted backup, its password typed twice as in
// Backup & Restore.
import React, { useState } from "react";
import { BACKUP_PASSWORD_HINT, backupPasswordProblem, downloadEncryptedBackup } from "../utils/encryptedBackup";

/** `onSaving(true)` while the backup downloads: the dialog waits for it. */
const BackupFirst: React.FC<{ busy: boolean; onSaving: (saving: boolean) => void }> = ({ busy, onSaving }) => {
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);

  const download = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") || "");
    const problem = backupPasswordProblem(password, String(form.get("repeat") || ""));
    if (problem) {
      setNote(problem);
      return;
    }
    setSaving(true);
    onSaving(true);
    try {
      setNote((await downloadEncryptedBackup(password)) ?? "");
    } catch {
      setNote("Failed to download backup."); // as Backup & Restore says it
    } finally {
      setSaving(false);
      onSaving(false);
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
        className="input" aria-label="Encrypt with password" aria-describedby="dialog-backup-password-rule" />
      <input type="password" name="repeat" placeholder="Repeat password" required autoComplete="new-password"
        className="input" aria-label="Repeat password" aria-describedby="dialog-backup-password-rule" />
      <button type="submit" disabled={busy || saving} className="btn btn-secondary">
        {saving ? "Processing..." : "Download backup"}
      </button>
      <p className="field-hint" id="dialog-backup-password-rule">{BACKUP_PASSWORD_HINT}</p>
      {note && <p className="field-hint" role="status">{note}</p>}
    </form>
  );
};

export default BackupFirst;
