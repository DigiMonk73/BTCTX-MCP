// The past-year warning (2.0 spec 5.8, #352): an add, an edit or a delete
// that would change the figures of a tax year before this one is saved only
// once the owner confirms it. The server's 409 says which years and what
// moves, with the fingerprint the same request is sent again with
// (backend/services/past_years.py).
import axios from "axios";

/** What the owner is asked about: the warning differs only in its words. */
export type PastYearKind = "add" | "edit" | "delete";

/** Why a write is asked about again: the ledger changed after the owner's
 * confirm, or after the page's own (an add to a year kept quiet). */
export type WarnedAgain = "confirmed" | "quiet";

/** A row the save changes, as Ledger Review lists one (backend/services/year_changes.py). */
export interface PastYearChange {
  /** null for the row an add makes */
  id: number | null;
  date: string;
  type: string;
  purpose: string | null;
  source: string | null;
  amount: string;
  unit?: "BTC" | "USD";
  realized_gain_usd: string | null;
  issue: string;
  /** What moves, in words */
  change: string;
  /** The tax years its figures are in, before and after the save */
  years: number[];
}

/** The 409's body. */
export interface PastYearWarning {
  detail: string;
  years: number[];
  changes: PastYearChange[];
  /** What the save also applies: rules fixed since those rows were saved */
  pending: PastYearChange[];
  /** Why Recalculate Ledger can't run now, when it can't */
  recalc_error: string | null;
  /** false when the server ran out of time to work out exactly what moves,
   * and names every year the write can reach instead */
  exact: boolean;
  why_not_exact: string | null;
  confirm: string;
}

const textOrNull = (value: unknown): string | null => (typeof value === "string" ? value : null);
const listOf = <T>(value: unknown): T[] => (Array.isArray(value) ? (value as T[]) : []);

/** The past-year warning in a failed request; null for any other failure.
 * Only this 409 carries a `confirm`: the page-version 409 and Delete All's
 * keep their own handling. */
export function pastYearWarning(err: unknown): PastYearWarning | null {
  if (!axios.isAxiosError(err) || err.response?.status !== 409) return null;
  const data = (err.response.data ?? {}) as Record<string, unknown>;
  const confirm = textOrNull(data.confirm);
  if (confirm === null) return null;
  return {
    detail: textOrNull(data.detail) ?? "",
    years: listOf<number>(data.years),
    changes: listOf<PastYearChange>(data.changes),
    pending: listOf<PastYearChange>(data.pending),
    recalc_error: textOrNull(data.recalc_error),
    exact: data.exact !== false,
    why_not_exact: textOrNull(data.why_not_exact),
    confirm,
  };
}

/** "2025", "2024 and 2025", "2023, 2024 and 2025": oldest first, each once. */
export function yearsInWords(years: readonly number[]): string {
  const words = [...new Set(years)].sort((a, b) => a - b).map(String);
  if (words.length < 2) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words[words.length - 1]}`;
}

/** "Tax year 2025", "Tax years 2024 and 2025"; "" for none. */
export function taxYearsLabel(years: readonly number[]): string {
  if (years.length === 0) return "";
  return `${new Set(years).size === 1 ? "Tax year" : "Tax years"} ${yearsInWords(years)}`;
}

export interface ChangesInYears {
  label: string;
  items: PastYearChange[];
}

/** The changes under the tax years they're in, in the order the server
 * lists them (by date). A row moved from one year to another is under both
 * together, never listed twice. */
export function byTaxYears(items: readonly PastYearChange[]): ChangesInYears[] {
  const groups = new Map<string, PastYearChange[]>();
  for (const item of items) {
    const label = taxYearsLabel(listOf<number>(item.years));
    groups.set(label, [...(groups.get(label) ?? []), item]);
  }
  return [...groups].map(([label, listed]) => ({ label, items: listed }));
}

// The tax years the owner chose not to be asked about again for adds. Kept
// here, never in the browser's storage: the choice lasts while the page is
// open, and a reload asks again (the owner's decision).
const quietYears = new Set<number>();

/** Adds to these years are confirmed without asking, until the page reloads. */
export function keepAddsQuiet(years: readonly number[]): void {
  for (const year of years) quietYears.add(year);
}

/** Every year the warning names is one the owner keeps quiet (none named: asked). */
export function addsQuietFor(years: readonly number[]): boolean {
  return years.length > 0 && years.every((year) => quietYears.has(year));
}

/** For tests: the page as freshly loaded. */
export function forgetQuietYears(): void {
  quietYears.clear();
}
