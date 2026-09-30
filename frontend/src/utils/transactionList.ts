// The Transactions page's list: its order, the page shown and the day
// headings.

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
