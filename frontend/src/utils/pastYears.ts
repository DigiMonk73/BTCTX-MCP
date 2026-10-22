// The past-year warning (spec 5.8): a write that changes the figures of an
// earlier tax year answers 409 with what it changes, and saves only when sent
// again with ?confirm=<the 409's fingerprint>. One shape for every write it
// covers: a transaction's add, edit or delete, and an exchange's 1099-DA switch.
import axios from "axios";
import { reviewAmount, reviewAccounts, typeWithSourceOrPurpose } from "./transactionList";

export interface PastYearsItem {
  id: number;
  date: string;
  type: string;
  source?: string | null;
  purpose?: string | null;
  amount: string;
  unit?: string;
  accounts?: string[];
  change: string;
  years: number[];
}

export interface PastYearsWarning {
  detail: string;
  years: number[];
  changes: PastYearsItem[];
  pending: PastYearsItem[];
  recalc_error?: string | null;
  confirm: string;
}

export function pastYearsWarning(error: unknown): PastYearsWarning | null {
  if (!axios.isAxiosError(error) || error.response?.status !== 409) return null;
  const data: unknown = error.response.data;
  if (typeof data !== "object" || data === null) return null;
  const body = data as {
    detail?: unknown;
    years?: unknown;
    changes?: PastYearsItem[] | null;
    pending?: PastYearsItem[] | null;
    recalc_error?: string | null;
    confirm?: unknown;
  };
  if (typeof body.confirm !== "string" || !Array.isArray(body.years)) return null;
  return {
    detail: String(body.detail ?? ""),
    years: body.years as number[],
    changes: body.changes ?? [],
    pending: body.pending ?? [],
    recalc_error: body.recalc_error ?? null,
    confirm: body.confirm,
  };
}

export function confirmed(confirm?: string): { params: { confirm: string } } | undefined {
  if (!confirm) return undefined;
  return { params: { confirm } };
}

export function yearsText(years: number[]): string {
  if (years.length === 0) return "";
  const earlier = years.slice(0, -1);
  const last = String(years[years.length - 1]);
  if (earlier.length === 0) return last;
  return `${earlier.join(", ")} and ${last}`;
}

export function itemText(item: PastYearsItem): string {
  return `${item.date} · ${typeWithSourceOrPurpose(item)} · ${reviewAmount(item)}`
    + `${reviewAccounts(item)}: ${item.change}`;
}

// The years whose adds the owner said not to ask about again (the owner's
// decision "Offer it for adds", 2026-10-16). Kept only while the page is open:
// a reload asks again. Edits and deletes always ask.
const quietYears = new Set<number>();

export function addsSkipAsking(years: number[]): boolean {
  return years.length > 0 && years.every((year) => quietYears.has(year));
}

export function stopAskingForAdds(years: number[]): void {
  for (const year of years) quietYears.add(year);
}

export function askForAddsAgain(): void {
  quietYears.clear();
}
