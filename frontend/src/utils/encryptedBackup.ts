// The encrypted backup (POST /api/backup/download), which Restore brings back
// (POST /api/backup/restore): from Settings' Backup & Restore, and offered
// before Delete All (#256).
import api from "../api";
import { PASSWORD_RULE, passwordTooShort } from "./credentials";
import { downloadMessage } from "./desktopDownload";

/** Under the password fields: a new backup's password follows the login
 * passwords' rule (backend/routers/backup.py, #204). */
export const BACKUP_PASSWORD_HINT =
  `${PASSWORD_RULE} Keep it: without it the backup can't be opened. ` +
  "A backup made earlier with a shorter password still restores.";

/** Why these two typed passwords can't make a backup, or null when they can
 * (passwordTooShort counts as the server does). */
export function backupPasswordProblem(password: string, repeat: string): string | null {
  if (passwordTooShort(password)) return `The password is too short. ${PASSWORD_RULE}`;
  if (password !== repeat) return "The two passwords don't match.";
  return null;
}

/** Download it, encrypted with `password`; what to tell the owner (where the
 * Mac app saved it, or that it downloaded), or null when the save was
 * cancelled. Throws when the server can't make it. */
export async function downloadEncryptedBackup(password: string): Promise<string | null> {
  const formData = new FormData();
  formData.append("password", password);
  const res = await api.post("/backup/download", formData, { responseType: "blob" });
  return downloadMessage(new Blob([res.data]), "bitcoin_backup.btx", "btx", "Backup");
}

/** A restore's answer: `notice` when something of the backup wasn't kept,
 * such as a tax timezone BitcoinTX doesn't know (#407). */
export interface RestoreAnswer {
  message?: string;
  notice?: string;
}

/** What Settings says after a restore, and whether it waits for the owner to
 * read a notice before the login page, rather than moving on after 2 s. */
export function restoreOutcome(answer: RestoreAnswer): { message: string; waits: boolean } {
  const message = answer.message || "Backup restored. Redirecting to login...";
  return answer.notice ? { message: `${message} ${answer.notice}`, waits: true } : { message, waits: false };
}
