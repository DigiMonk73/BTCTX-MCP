/**
 * Where the sidebar converter's Date mode asks this BitcoinTX for a price
 * (#145): the hour on this device's clock, as the transaction form's Date &
 * Time is (#260), else the day's 00:00 UTC price. null: the date and hour
 * name no moment (a five-digit year the date field lets through), which
 * would otherwise throw while the page draws.
 */
export function historyPriceUrl(date: string, hour: string): string | null {
  if (hour === "") return `/bitcoin/price/history?date=${date}`;
  const at = new Date(`${date}T${hour.padStart(2, "0")}:00`);
  if (Number.isNaN(at.getTime())) return null;
  return `/bitcoin/price/history?at=${encodeURIComponent(at.toISOString())}`;
}

// A number field's text: sign, digits, decimal point, exponent ("1e-8")
const DECIMAL = /^([+-]?)(\d*)(?:\.(\d*))?(?:e([+-]?\d+))?$/i;
const SATS_PER_BTC = 100_000_000;

/**
 * A typed BTC amount in satoshis, from its digits (#451): 0.29 as a float
 * times 100,000,000 is 28,999,999.99…, a satoshi too few once cut off.
 * Digits past the satoshi round to the nearest; null: no number typed.
 */
export function satsFromBtc(text: string): number | null {
  const parts = DECIMAL.exec(text.trim());
  if (!parts || !(parts[2] || parts[3])) return null;
  const [, sign, whole, fraction = "", exponent = "0"] = parts;
  // Past all the bitcoin there is, exactness means nothing (and the digits would be millions long)
  if (Math.abs(Number(exponent)) > 20) return Math.round(Number(text) * SATS_PER_BTC);
  const integer = whole.replace(/^0+/, "");
  const digits = integer + fraction;
  const end = integer.length + Number(exponent) + 8; // where the whole satoshis end in the digits
  const padded = digits.padEnd(end, "0");
  const sats = (end > 0 ? Number(padded.slice(0, end)) : 0) + (Number(padded[end] ?? "0") >= 5 ? 1 : 0);
  return sign === "-" && sats ? -sats : sats;
}

/** Dollars at a price in satoshis, rounded once to the nearest (#451); null: no dollars or no price. */
export function satsFromUsd(usd: number, price: number): number | null {
  return usd && price ? Math.round((usd * SATS_PER_BTC) / price) : null;
}
