// The Transactions page's list: its order, the page shown, the day
// headings and a row's gain line.
import { formatSignedUsd, parseDecimal } from "./format";

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

// A gift, donation or lost coins aren't a sale: no gain or loss of their own
// (the tax report says so), so no gain line either (#257). Spent is a sale.
const NOT_A_SALE = new Set(["gift", "donation", "lost"]);

/** A sell's or spend's gain: "Gain +$1.00 · +2.00% · Long-term"; "" for
 * anything else, or with no basis and no gain. */
export function gainLabel(tx: ITransaction): string {
  if (tx.type !== "Sell" && tx.type !== "Withdrawal") return "";
  if (tx.type === "Withdrawal" && NOT_A_SALE.has((tx.purpose ?? "").toLowerCase())) return "";
  if (tx.cost_basis_usd == null || tx.realized_gain_usd == null) return "";
  const gain = parseDecimal(tx.realized_gain_usd);
  const basis = parseDecimal(tx.cost_basis_usd);
  if (gain === 0 && basis === 0) return "";
  const term = tx.holding_period === "LONG" ? "Long-term" : tx.holding_period === "SHORT" ? "Short-term" : "";
  const pct = basis !== 0 ? `${gain >= 0 ? "+" : "\u2212"}${Math.abs((gain / basis) * 100).toFixed(2)}%` : "";
  return [`${gain >= 0 ? "Gain" : "Loss"} ${formatSignedUsd(gain)}`, pct, term].filter(Boolean).join(" \u00b7 ");
}
