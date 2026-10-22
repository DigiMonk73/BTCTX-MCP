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

/**
 * Date mode's line under the date and hour, once an hour is chosen (#555):
 * which price the server answered, in UTC as a price's hour always is. The
 * hour's own price, or, where none is stored for it, the 00:00 UTC price of
 * the hour's UTC day, which isn't always the date picked: 23:00 on Mar 1 in
 * Chicago gets Mar 2's. why: the reason, for a screen reader and the title.
 * null: no answer naming a moment.
 */
export function priceMomentLine(moment?: string, at?: string): { text: string; why: string | null } | null {
  if (!at || (moment !== "hour" && moment !== "day")) return null;
  const day = new Date(at).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
  const when = `${day}, ${at.slice(11, 16)} UTC`;
  return moment === "hour"
    ? { text: `Hour's price: ${when}`, why: null }
    : { text: `Day's price: ${when}`, why: "No price is stored for that hour." };
}

// A number field's text: sign, digits, decimal point, exponent ("1e-8")
const DECIMAL = /^([+-]?)(\d*)(?:\.(\d*))?(?:e([+-]?\d+))?$/i;
export const SATS_PER_BTC = 100_000_000;

/**
 * A typed BTC amount in satoshis, from its digits (#451): 0.29 as a float
 * times 100,000,000 is 28,999,999.99…, a satoshi too few once cut off.
 * Digits past the satoshi round to the nearest, an exact half to the even
 * count (#529); null: no number typed.
 */
export function satsFromBtc(text: string): number | null {
  const btc = typedDigits(text);
  if (!btc) return null;
  if (btc.huge) return Math.round(Number(text) * SATS_PER_BTC);
  const shift = 8 - btc.places; // satoshis: the digits times 10^shift
  return Number(shift >= 0 ? btc.digits * 10n ** BigInt(shift) : nearest(btc.digits, 10n ** BigInt(-shift)));
}

/**
 * Dollars at a price in satoshis, from the typed digits (#529): as floats,
 * $488.93 at $96,281.60 is 507,812.49999999994 satoshis, where it's exactly
 * 507,812.5. Rounded once (#451) to the nearest, an exact half to the even
 * count. The price is a number (the server's, or the one typed), whose
 * shortest text is its digits for any price to the cent. null: no dollars or
 * no price.
 */
export function satsFromUsd(usd: string, price: number): number | null {
  const dollars = typedDigits(usd);
  const perBtc = typedDigits(String(price));
  if (!dollars || !perBtc || !dollars.digits || !perBtc.digits) return null;
  if (dollars.huge || perBtc.huge) return Math.round((Number(usd) * SATS_PER_BTC) / price);
  // dollars × 10^8 ÷ price, each its digits over a power of ten
  const shift = 8 - dollars.places + perBtc.places;
  return Number(shift >= 0
    ? nearest(dollars.digits * 10n ** BigInt(shift), perBtc.digits)
    : nearest(dollars.digits, perBtc.digits * 10n ** BigInt(-shift)));
}

/**
 * A typed BTC amount's worth at a price, as the USD field writes it (#578):
 * exact from the digits, to the cent, an exact half cent to the even cent,
 * as the server works a value out from a price (Decimal's quantize), so the
 * converter shows the cent BitcoinTX would save. As floats, 0.5 BTC at
 * $96,281.61 is $48,140.81, where $48,140.805 is $48,140.80. "": no amount
 * or no price.
 */
export function usdFromBtc(btc: string, price: number): string {
  return usdText(btc, 0, price);
}

/** A typed number of satoshis' worth at a price, as usdFromBtc writes it. */
export function usdFromSats(sats: string, price: number): string {
  return usdText(sats, 8, price);
}

// The typed amount, `places` decimal places under a bitcoin, at the price
function usdText(text: string, places: number, price: number): string {
  const amount = typedDigits(text);
  const perBtc = typedDigits(String(price));
  if (!amount || !perBtc || !amount.digits || !perBtc.digits) return "";
  if (amount.huge || perBtc.huge) {
    const usd = (Number(text) / 10 ** places) * price;
    return usd ? String(Math.round(usd * 100) / 100) : "";
  }
  // cents: amount × price × 100, each its digits over a power of ten
  const shift = 2 - amount.places - places - perBtc.places;
  const product = amount.digits * perBtc.digits;
  const cents = shift >= 0 ? product * 10n ** BigInt(shift) : nearest(product, 10n ** BigInt(-shift));
  const size = cents < 0n ? -cents : cents;
  // As the field wrote a number of dollars: "48140.8", "150", "0"
  const dollars = `${size / 100n}.${String(size % 100n).padStart(2, "0")}`.replace(/\.?0+$/, "");
  return cents < 0n ? `-${dollars}` : dollars;
}

/**
 * A number field's text exactly: its digits (signed) over 10^places. huge:
 * an exponent far past all the bitcoin there is, or far under a satoshi,
 * where exactness means nothing and writing out the digits could take more
 * memory than there is. null: no number typed.
 */
function typedDigits(text: string): { digits: bigint; places: number; huge: boolean } | null {
  const parts = DECIMAL.exec(text.trim());
  if (!parts || !(parts[2] || parts[3])) return null;
  const [, sign, whole, fraction = "", exponent = "0"] = parts;
  const digits = BigInt(whole + fraction);
  return {
    digits: sign === "-" ? -digits : digits,
    places: fraction.length - Number(exponent),
    huge: Math.abs(Number(exponent)) > 20,
  };
}

/** num ÷ den to the nearest whole number, an exact half to the even one: the
 * rule for a value worked out from a price (AGENTS.md, "Prices"; #556). */
function nearest(num: bigint, den: bigint): bigint {
  const negative = num < 0n !== den < 0n;
  const [n, d] = [num < 0n ? -num : num, den < 0n ? -den : den];
  const whole = n / d;
  const twice = 2n * (n % d);
  const up = twice > d || (twice === d && whole % 2n === 1n);
  const count = up ? whole + 1n : whole;
  return negative ? -count : count;
}
