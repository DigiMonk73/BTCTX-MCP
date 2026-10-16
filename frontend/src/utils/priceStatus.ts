/**
 * The price status line (#145, plan 2.3): one line, words first, from
 * GET /api/bitcoin/price/status (backend/services/price_status.py). The
 * colour and the icon only repeat the words. Times are this device's clock
 * (#260): the tax timezone decides tax years, not the time of day shown.
 */

import type { Host, PriceSource } from "./priceSource";

export type Problem =
  | "mempool_no_answer"
  | "mempool_untrusted_certificate"
  | "mempool_missing"
  | "public_no_answer"
  | "tor_no_answer";

export interface HistoryStatus {
  until: string | null;
  first_year: number | null;
  shipped: boolean;
  years_total: number;
  years_done: number;
  state: "complete" | "downloading" | "failed" | "not_allowed" | "waiting";
  failed_at: string | null;
  /** The download failed because Bitstamp refused it (a block or a challenge page). */
  refused?: boolean;
  mismatched: number[];
}

/** What Bitstamp gives Tor's exits (#241), said wherever Tor and the history meet. */
export const TOR_REFUSED =
  "Through Tor, Bitstamp currently refuses BitcoinTX's requests, so the hourly history and past prices don't download; only the live price works. " +
  "Choose Public price sites without Tor (on StartOS: turn off Use Tor in its Price Source & Privacy action) to download them " +
  "(once checked, the hourly history stays), use your own Mempool for newer values, or type them.";

export interface PriceStatus {
  source: PriceSource | "unset";
  managed: boolean;
  invalid: boolean;
  waiting: boolean;
  host: Host;
  last_ok: { at: string; from: string } | null;
  last_problem: { at: string; what: Problem } | null;
  /** Your Mempool's last problem, kept when the backup then fails too. */
  last_mempool_problem?: { at: string; what: Problem } | null;
  history: HistoryStatus;
}

export type Tone = "ok" | "idle" | "warning";

export interface StatusLine {
  tone: Tone;
  text: string;
}

/** What the card's settings add: the backup and Tor, as saved. */
export interface StatusContext {
  backup: boolean;
  tor: boolean;
  /** The Mempool's certificate may be trusted on the card (#188). */
  trustable?: boolean;
}

/** "2:04 pm" on this device's clock, as the transaction list shows times (#260). */
export function clock(iso: string): string {
  return new Date(iso)
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    .replace(/\s(AM|PM)$/, (_, m: string) => " " + m.toLowerCase());
}

const PUBLIC_SITES = "public price sites";

function mempoolReason(what: Problem, at: string): string {
  if (what === "mempool_untrusted_certificate") {
    return "Your Mempool's certificate isn't trusted (a private one, like StartOS's home-network address), so BitcoinTX can't use it.";
  }
  if (what === "mempool_missing") return "Mempool isn't installed on this server yet.";
  return `Your Mempool didn't answer at ${clock(at)}.`;
}

function mempoolFix(what: Problem, managed: boolean, backup: boolean, trustable = false): string {
  if (what === "mempool_untrusted_certificate") {
    return trustable
      ? "There's no newer price until you trust it: if it's your own server, use Trust this server below."
      : "There's no newer price: use its http:// or .onion address instead, or on StartOS choose My Mempool on this server.";
  }
  if (what === "mempool_missing") return "Install and start it, or choose another source in StartOS.";
  return managed || backup
    ? "Type newer values meanwhile."
    : 'Type newer values meanwhile, or tick "If it can\'t answer, ask public price sites".';
}

function capital(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function newer(a: string | undefined, b: string | undefined): boolean {
  return (a ?? "") > (b ?? "");
}

/** Why your Mempool last failed, kept when the backup failed after it. */
export function mempoolProblem(st: PriceStatus): Problem | null {
  const problem = st.last_problem;
  return (problem?.what.startsWith("mempool") ? problem : (st.last_mempool_problem ?? null))?.what ?? null;
}

function mempoolLine(st: PriceStatus, ctx: StatusContext): StatusLine {
  const { last_ok: ok, last_problem: problem } = st;
  // Why your Mempool last failed, kept when the backup failed after it
  const mine = problem?.what.startsWith("mempool") ? problem : (st.last_mempool_problem ?? null);
  const reason = mine ? mempoolReason(mine.what, mine.at) : "Your Mempool didn't answer.";
  if (problem && newer(problem.at, ok?.at)) {
    if (problem === mine) {
      return { tone: "warning", text: `${reason} ${mempoolFix(problem.what, st.managed, ctx.backup, ctx.trustable)}` };
    }
    const at = clock(problem.at);
    const backup = problem.what === "tor_no_answer"
      ? `Public price sites didn't answer through Tor either, at ${at}. Is Tor running?`
      : `${capital(PUBLIC_SITES)} didn't answer either, at ${at}.`;
    return { tone: "warning", text: `${reason} ${backup}` };
  }
  if (ok && ok.from !== "mempool") {
    // #178: never "from your Mempool" while the backup gives the prices
    return { tone: "warning", text: `${reason} Public price sites answered instead at ${clock(ok.at)}.` };
  }
  if (ok) return { tone: "ok", text: `Newer prices from your Mempool. Last price ${clock(ok.at)}.` };
  return { tone: "idle", text: "Newer prices will come from your Mempool." };
}

function publicLine(st: PriceStatus, ctx: StatusContext): StatusLine {
  const { last_ok: ok, last_problem: problem } = st;
  const via = ctx.tor ? ", through Tor" : "";
  if (problem && newer(problem.at, ok?.at)) {
    const at = clock(problem.at);
    return problem.what === "tor_no_answer"
      ? { tone: "warning", text: `Public price sites didn't answer through Tor at ${at}. Is Tor running?` }
      : { tone: "warning", text: `Public price sites didn't answer at ${at}. BitcoinTX asks again in a few minutes.` };
  }
  if (ok) return { tone: "ok", text: `Newer prices from public price sites${via}. Last price ${clock(ok.at)}.` };
  return { tone: "idle", text: `Newer prices will come from public price sites${via}.` };
}

/** The status line for the choice in use. */
export function statusLine(st: PriceStatus, ctx: StatusContext): StatusLine {
  if (st.invalid) {
    return { tone: "warning", text: "This server's price settings aren't valid, so nothing is contacted." };
  }
  if (st.waiting) return { tone: "idle", text: "Waiting for you to confirm: nothing is contacted until you do." };
  if (st.source === "unset") return { tone: "idle", text: "Not chosen yet: nothing is contacted." };
  if (st.source === "off") return { tone: "idle", text: "Fully offline: nothing is contacted. Type newer values yourself." };
  return st.source === "mempool" ? mempoolLine(st, ctx) : publicLine(st, ctx);
}

/** The card's first line: where the hourly history is (#145, the amendment's A). */
export interface HistoryLine extends StatusLine {
  /** Years done of all, while downloading. */
  progress?: { done: number; total: number };
}

function untilDay(until: string): string {
  return new Date(until.replace(/Z$/, ":00Z")).toLocaleDateString("en-US", {
    month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
  });
}

/** The hourly history's line for the card, given the choice in use. */
export function historyLine(st: PriceStatus, ctx: StatusContext): HistoryLine | null {
  const h = st.history;
  // Invalid server settings: the status line says why; "your choice" would be wrong
  if (!h.until || !h.first_year || st.invalid) return null;
  const span = `${h.first_year} to ${untilDay(h.until)}`;
  const tor = ctx.tor ? " through Tor" : "";
  if (h.shipped) return { tone: "ok", text: `Built in: every hourly price from ${span}. Works offline, nothing to set.` };
  if (h.state === "complete") {
    return { tone: "ok", text: `Hourly prices, ${span}: downloaded and checked. They work offline from now on, whatever you choose.` };
  }
  if (h.state === "downloading") {
    return {
      tone: "idle",
      text: `Downloading the hourly history from Bitstamp${tor}: ${h.years_done} of ${h.years_total} years, each checked. You can keep working; until a year arrives, its values use the day's price.`,
      progress: { done: h.years_done, total: h.years_total },
    };
  }
  const chosen = st.source !== "unset" && !st.waiting;
  if (h.state === "not_allowed" && chosen) {
    return { tone: "idle", text: `The hourly history (${span}) needs a one-time download from Bitstamp, which your choice doesn't allow.` };
  }
  return problemLine(h, span, ctx) ?? (chosen ? pendingLine(h, span) : notChosenLine(span));
}

// Tried again when a value next needs a missing year, or at the next start (hourly_prices.start_download)
const LATER = "when BitcoinTX next needs it or restarts";

function problemLine(h: HistoryStatus, span: string, ctx: StatusContext): HistoryLine | null {
  if (h.state === "failed" && ctx.tor && h.refused) {
    return { tone: "warning", text: `The hourly history didn't download. ${TOR_REFUSED}` };
  }
  if (h.state === "failed") {
    const why = ctx.tor ? "Bitstamp didn't answer through Tor: is Tor running?" : h.refused ? "Bitstamp refused it." : "Bitstamp didn't answer.";
    return { tone: "warning", text: `The hourly history didn't download: ${why} It's tried again ${LATER}, at least 10 minutes later. Meanwhile values use the day's price.` };
  }
  if (h.mismatched.length > 0) {
    const years = h.mismatched.join(", ");
    const verb = h.mismatched.length > 1 ? "use" : "uses";
    return { tone: "warning", text: `Bitstamp's prices for ${years} didn't match BitcoinTX's fingerprint, so ${years} ${verb} the day's price. Tried again a day later, ${LATER}.` };
  }
  return null;
}

function pendingLine(h: HistoryStatus, span: string): HistoryLine {
  const done = h.years_done > 0 ? `${h.years_done} of ${h.years_total} years downloaded and checked` : "not downloaded yet";
  return { tone: "idle", text: `Hourly prices, ${span}: ${done}. BitcoinTX downloads the rest from Bitstamp ${LATER}. Meanwhile those values use the day's price.` };
}

function notChosenLine(span: string): HistoryLine {
  return {
    tone: "idle",
    text: `Hourly prices, ${span}: downloaded once from Bitstamp when you choose Public price sites, or My own Mempool with its backup, each year checked against a fingerprint that comes with BitcoinTX. Nothing in the download names your dates.`,
  };
}

/** What a blank value needs when nothing is asked: the way forward, in the hint's words. */
function noAsking(st: PriceStatus): string {
  if (st.invalid) return "type it: this server's price settings aren't valid";
  if (st.waiting) return "confirm where BitcoinTX gets prices (on the Dashboard), or type it";
  if (st.source === "unset") return "choose where BitcoinTX gets prices (on the Dashboard), or type it";
  return "type it: you chose Nobody";
}

/** Whether BitcoinTX asks anyone for a price now: not with Nobody, before a choice or its confirmation, or invalid settings. */
function asking(st: PriceStatus): boolean {
  return !st.invalid && !st.waiting && (st.source === "public" || st.source === "mempool");
}

/** Your Mempool alone: it has prices only from when it began recording (as olderValuesNote says). */
function mempoolOnly(st: PriceStatus, ctx: StatusContext): boolean {
  return st.source === "mempool" && !ctx.backup;
}

/** Where newer prices come from: public sites, or your Mempool, with its backup or alone. */
function newerFrom(st: PriceStatus, ctx: StatusContext): string {
  if (st.source === "public") return "public price sites";
  return ctx.backup ? "your Mempool, else public price sites" : "your Mempool where it has them; otherwise type it";
}

// Through Tor, Bitstamp refuses BitcoinTX's requests (#241): no past prices download
const TOR_REFUSED_SHORT = " Through Tor, Bitstamp currently refuses BitcoinTX's requests, so an older value may have no price: then type it.";

/**
 * Where a blank value's price comes from, after the form's "Leave blank to
 * use the BTC price when that hour began" (#208, plan 2.5), as price_at finds
 * it (services/hourly_prices.py): the hourly prices BitcoinTX holds, then the
 * choice (your Mempool only where it recorded, else typed; with its backup,
 * public sites); when nothing is asked, what to do. From the status and the
 * saved choice's backup and Tor, which ask nobody.
 */
export function blankPriceSource(st: PriceStatus, ctx: StatusContext): string {
  const h = st.history;
  if (h.until && (h.shipped || h.state === "complete")) {
    const stored = `Hourly prices from ${h.first_year ?? 2013} to ${untilDay(h.until)} are stored in BitcoinTX`;
    return asking(st) ? `${stored}; newer ones come from ${newerFrom(st, ctx)}.` : `${stored}; after that, ${noAsking(st)}.`;
  }
  if (!asking(st)) return `Unless BitcoinTX already has that hour's price, ${noAsking(st)}.`;
  if (mempoolOnly(st, ctx)) return "Your Mempool has prices only from when it began recording: for an older hour, type the value.";
  const refused = ctx.tor && h.state === "failed" && h.refused ? TOR_REFUSED_SHORT : "";
  return `It comes from ${newerFrom(st, ctx)}.${refused}`;
}

/**
 * The same for a day's price (an inheritance's, on the date of death): what
 * to do where nothing is asked, or your Mempool alone hasn't that day; ""
 * where the day's price is found (#208).
 */
export function blankDayPriceSource(st: PriceStatus, ctx: StatusContext): string {
  if (!asking(st)) return `Unless BitcoinTX already has that day's price, ${noAsking(st)}.`;
  return mempoolOnly(st, ctx) ? "Your Mempool has prices only from when it began recording: for an older date, type the value." : "";
}

/** Under a chosen Mempool without its backup, or Nobody: what that means for older values. */
export function olderValuesNote(source: string, backup: boolean, h: HistoryStatus | undefined): string | null {
  if (h?.shipped || h?.state === "complete") return null;
  if (source === "mempool" && !backup) {
    return "It has hourly prices only from when it began recording. Older values are typed, unless you tick the backup.";
  }
  if (source === "off") {
    return "Older values are typed, unless the history is already downloaded. To have it and then ask nobody: choose Public price sites until the download finishes, then Nobody. The history stays.";
  }
  return null;
}
