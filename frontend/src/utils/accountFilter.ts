// The Transactions page's account filter (2.0 spec 5.13, P7's mockups):
// choices grouped by kind, applied in the browser like the page's sort.
import { yours } from "./accounts";

/** "all"; "kind:wallet" (every wallet); "account:101" (one bank or wallet);
 * "exchange:2" (both of an exchange's accounts). */
export type AccountChoice = string;

export const ALL_ACCOUNTS: AccountChoice = "all";

export interface FilterOption {
  value: AccountChoice;
  label: string;
}

export interface FilterGroup {
  label: "Wallets" | "Exchanges" | "Banks";
  options: FilterOption[];
}

const GROUPS: [AccountKind, FilterGroup["label"], string][] = [
  ["wallet", "Wallets", "All wallets"], ["exchange", "Exchanges", "All exchanges"], ["bank", "Banks", "All banks"],
];

/** A kind's choices: its accounts (an exchange once, by its name) in the book's order, hidden ones marked. */
function kindOptions(book: AccountBook, kind: AccountKind): FilterOption[] {
  const own = new Set(yours(book));
  const options = new Map<AccountChoice, FilterOption>();
  for (const account of book.filter((a) => own.has(a.id) && a.kind === kind)) {
    const exchange = kind === "exchange" && account.exchange_id !== null;
    const value = exchange ? `exchange:${account.exchange_id}` : `account:${account.id}`;
    const name = exchange ? account.exchange ?? account.name : account.name;
    options.set(value, { value, label: account.hidden ? `${name} (hidden)` : name });
  }
  return [...options.values()];
}

/** Each kind with accounts, after its "All wallets" (and so on) when it has more than one. */
export function filterGroups(book: AccountBook): FilterGroup[] {
  return GROUPS.flatMap(([kind, label, all]) => {
    const options = kindOptions(book, kind);
    if (options.length === 0) return [];
    return [{ label, options: options.length > 1 ? [{ value: `kind:${kind}`, label: all }, ...options] : options }];
  });
}

/** Whether a row names the chosen account (either side: a transfer shows under both). */
export function matchesFilter(
  tx: { from_account_id: number | null; to_account_id: number | null }, choice: AccountChoice, book: AccountBook,
): boolean {
  if (choice === ALL_ACCOUNTS) return true;
  const [what, key] = choice.split(":");
  const sides = book.filter((a) => a.id === tx.from_account_id || a.id === tx.to_account_id);
  if (what === "kind") return sides.some((a) => a.kind === key);
  if (what === "exchange") return sides.some((a) => a.kind === "exchange" && String(a.exchange_id) === key);
  if (what === "account") return sides.some((a) => String(a.id) === key);
  return false;
}

/** "3 of 7 transactions". */
export function filterCount(shown: number, all: number): string {
  return `${shown} of ${all} transaction${all === 1 ? "" : "s"}`;
}
