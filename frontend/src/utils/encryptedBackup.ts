// The encrypted backup (POST /api/backup/download), which Restore brings back:
// from Settings' Backup & Restore, and offered before Delete All (#256).
import api from "../api";
import { downloadMessage } from "./desktopDownload";

/** Download it, encrypted with `password`; what to tell the owner (where the
 * Mac app saved it, or that it downloaded), or null when the save was
 * cancelled. Throws when the server can't make it. */
export async function downloadEncryptedBackup(password: string): Promise<string | null> {
  const formData = new FormData();
  formData.append("password", password);
  const res = await api.post("/backup/download", formData, { responseType: "blob" });
  return downloadMessage(new Blob([res.data]), "bitcoin_backup.btx", "btx", "Backup");
}
