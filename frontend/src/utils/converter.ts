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
