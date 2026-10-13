/**
 * Wall-clock times in a named timezone (the tax timezone), worked out with
 * Intl: no library, and the browser's own timezone never enters.
 */

/** How far `timeZone`'s wall clock is ahead of UTC at the instant `utcMs`, in ms. */
function offsetMs(utcMs: number, timeZone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone, hourCycle: "h23", year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(new Date(utcMs));
  const part = (type: string) => Number(parts.find((p) => p.type === type)?.value);
  return Date.UTC(part("year"), part("month") - 1, part("day"), part("hour"), part("minute"), part("second")) - utcMs;
}

/** "2024-03-01" at hour 9 in `timeZone`, as an ISO 8601 UTC instant ("2024-03-01T15:00:00.000Z" in Chicago). */
export function zonedHourToIso(date: string, hour: number, timeZone: string): string {
  const [y, m, d] = date.split("-").map(Number);
  const wall = Date.UTC(y, m - 1, d, hour);
  let utc = wall;
  for (let i = 0; i < 3; i += 1) utc = wall - offsetMs(utc, timeZone); // settles across a DST change
  return new Date(utc).toISOString();
}

/** The UTC hour of an instant, as "15:00 UTC". */
export function utcHourLabel(iso: string): string {
  return `${new Date(iso).toISOString().slice(11, 16)} UTC`;
}
