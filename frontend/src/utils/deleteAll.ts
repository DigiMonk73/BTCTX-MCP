// Deleting every transaction (#256): what goes, said before it goes, and the
// typed confirmation the server needs (backend/services/wipe.py).
import axios from "axios";

/** What a delete would take (GET /api/transactions/delete_all, or a 409). */
export interface LedgerExtent {
  transactions: number;
  first_year: number | null;
  last_year: number | null;
}

/** What the owner types to confirm, and the server checks. */
export const CONFIRMATION = "DELETE";

/** "118 transactions, 2023–2026" ("1 transaction, 2024"). */
export function describeExtent({ transactions, first_year, last_year }: LedgerExtent): string {
  const noun = transactions === 1 ? "transaction" : "transactions";
  const years = first_year !== last_year ? `${first_year}–${last_year}` : `${first_year}`;
  return first_year == null ? `${transactions} ${noun}` : `${transactions} ${noun}, ${years}`;
}

/** The server's 409 when a delete needs the confirmation: what would go;
 * null for any other failure. */
export function extentToConfirm(err: unknown): LedgerExtent | null {
  if (!axios.isAxiosError(err) || err.response?.status !== 409) return null;
  const data = err.response.data as Partial<LedgerExtent> | undefined;
  return typeof data?.transactions === "number" ? (data as LedgerExtent) : null;
}
