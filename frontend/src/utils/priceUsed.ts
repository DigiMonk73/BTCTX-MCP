/**
 * How the form says where a saved value came from (#145, plan 2.5): the
 * stored price BitcoinTX filled it in from (its hour or day, and source),
 * or that it was typed. The transaction API gives the price (price_used).
 */

const SOURCE_NAMES: Record<string, string> = { mempool: "your Mempool", bitstamp: "Bitstamp", kraken: "Kraken" };

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

/** "$50,083.00 at 14:00 UTC, Mar 1, 2024 · Bitstamp", or the day's 00:00 UTC price. */
export function priceUsedWords(p: PriceUsed): string {
  const usd = `$${Number(p.usd_per_btc).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  const when = p.moment === "hour" ? ` at ${p.at.slice(11, 16)} UTC, ${day(p.at)}` : `, the day's price (00:00 UTC) on ${day(p.at)}`;
  const source = SOURCE_NAMES[p.source] ?? (p.source ? p.source.charAt(0).toUpperCase() + p.source.slice(1) : "");
  return source ? `${usd}${when} · ${source}` : `${usd}${when}`;
}

/**
 * The note under a value the form shows: "From the price: …" while it's the
 * value BitcoinTX filled in, "Typed: …" for one the owner typed; nothing for
 * a new transaction, or once the value is changed.
 */
export function valueOrigin(
  fromPrice: boolean | undefined,
  stored: number | undefined,
  shown: number | undefined,
  used: PriceUsed | null | undefined,
): string | null {
  if (fromPrice === undefined || stored === undefined) return null; // a new transaction
  if (!fromPrice && !stored) return null; // blank or 0: the save prices it (review of #190)
  if (shown === undefined || Number.isNaN(shown) || Math.abs(shown - stored) > 0.004) return null; // being changed
  if (!fromPrice) return "Typed: you typed this value; it's kept as it is.";
  return used
    ? `From the price: ${priceUsedWords(used)}. Type a value to replace it.`
    : "From the price. Type a value to replace it.";
}
