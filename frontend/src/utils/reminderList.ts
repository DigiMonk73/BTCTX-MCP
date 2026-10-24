/**
 * A Ledger review reminder's button (#128): what its folded list holds.
 * My BTC and Gift deposits without a date originally acquired, or exchange
 * Sells the exchange's Form 1099-DA may show differently (2.0, #349).
 */

const ROWS: Record<string, string> = { original_date_missing: "deposit", sale_may_differ_from_1099da: "sale" };

/** "Show the 2 deposits", "Show the 1 sale". */
export function showTheList(key: string, count: number): string {
  return `Show the ${count} ${ROWS[key] ?? "transaction"}${count === 1 ? "" : "s"}`;
}
