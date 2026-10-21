// The Transactions page's list: its order, the page shown, the day
// headings and a row's gain line.
import { formatSignedUsd, parseDecimal } from "./format";
import { isNotSold, listedPurpose, listedSource } from "./purposes";

/** One account's history (5.13): the rows naming `accountId` on either side; every row for undefined. */
export function byAccount(transactions: ITransaction[], accountId: number | undefined): ITransaction[] {
  if (accountId === undefined) return transactions;
  return transactions.filter((tx) => tx.from_account_id === accountId || tx.to_account_id === accountId);
}

/** Newest first: by date, or by when they were added (id). */
export function sortTransactions(transactions: ITransaction[], sortMode: SortMode): ITransaction[] {
  return [...transactions].sort((a, b) => {
    if (sortMode === "TIMESTAMP_DESC") {
      return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
    }
    return b.id - a.id;
  });
}

/** The page to show, kept between the first and the last, and its items. */
export function pageOf<T>(items: T[], requestedPage: number, pageSize: number) {
  const totalPages = Math.ceil(items.length / pageSize);
  const page = Math.min(Math.max(requestedPage, 1), totalPages || 1);
  const start = (page - 1) * pageSize;
  return { page, totalPages, items: items.slice(start, start + pageSize) };
}

/** Transactions under their day's heading ("Jun 1, 2024", local time), in
 * list order. */
export function groupByDay(transactions: ITransaction[]): [string, ITransaction[]][] {
  const groups: Record<string, ITransaction[]> = {};
  for (const tx of transactions) {
    const day = new Date(tx.timestamp).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    if (!groups[day]) groups[day] = [];
    groups[day].push(tx);
  }
  return Object.entries(groups);
}

/** A sale's gain: "Gain +$1.00 · +2.00% · Long-term" for a Sell or a
 * Withdrawal, "" with no basis and no gain. A gift, a donation or lost coins
 * aren't sales, so they get none (#257). */
export function gainLabel(tx: ITransaction): string {
  if (tx.type !== "Sell" && tx.type !== "Withdrawal") return "";
  if (tx.type === "Withdrawal" && isNotSold(tx.purpose)) return "";
  if (tx.cost_basis_usd == null || tx.realized_gain_usd == null) return "";
  const gain = parseDecimal(tx.realized_gain_usd);
  const basis = parseDecimal(tx.cost_basis_usd);
  if (gain === 0 && basis === 0) return "";
  const term = tx.holding_period === "LONG" ? "Long-term" : tx.holding_period === "SHORT" ? "Short-term" : "";
  const pct = basis !== 0 ? `${gain >= 0 ? "+" : "\u2212"}${Math.abs((gain / basis) * 100).toFixed(2)}%` : "";
  return [`${gain >= 0 ? "Gain" : "Loss"} ${formatSignedUsd(gain)}`, pct, term].filter(Boolean).join(" \u00b7 ");
}

/** A transaction, or one of Ledger Review's items. */
type Described = { type: string; source?: string | null; purpose?: string | null };

/** A deposit's source or a withdrawal's purpose as the list shows it: in its
 * listed spelling (an older version may have saved "spent", #273), "" for
 * none. */
export function sourceOrPurpose(tx: Described): string {
  const shown = tx.type === "Deposit" ? listedSource(tx.source) : listedPurpose(tx.purpose);
  return shown === "N/A" ? "" : shown;
}

/** A Ledger Review item's amount: "0.10000000 BTC", or "$500.00" for a move of dollars. */
export function reviewAmount(item: { amount: string; unit?: string }): string {
  return item.unit === "USD" ? `$${item.amount}` : `${item.amount} BTC`;
}

/** "Withdrawal (Spent)", or the type alone with no source or purpose ("Sell"),
 * as Ledger Review lists an item. */
export function typeWithSourceOrPurpose(item: Described): string {
  const extra = sourceOrPurpose(item);
  return extra ? `${item.type} (${extra})` : item.type;
}
