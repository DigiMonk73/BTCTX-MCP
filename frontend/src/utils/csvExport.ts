// The CSV export (GET /api/backup/csv), from Settings' Backup & Restore.
import { toDatetimeLocal } from "./transactionForm";

/** The export's file name, dated by this device's clock as the screens show
 * dates: the UTC day would name an evening's export in Chicago for the next
 * day (#534). */
export function csvExportName(now: Date): string {
  return `btctx_transactions_${toDatetimeLocal(now).slice(0, 10)}.csv`;
}
