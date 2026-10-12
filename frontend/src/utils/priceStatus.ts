/**
 * The price status line (#145, plan 2.3): one line, words first, from
 * GET /api/bitcoin/price/status (backend/services/price_status.py). The
 * colour and the icon only repeat the words. Times are in the tax timezone.
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
  mismatched: number[];
}

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
  timezone: string;
}

/** "2:04 pm" in the tax timezone. */
export function clock(iso: string, timezone: string): string {
  return new Date(iso)
    .toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: timezone })
    .replace(/\s(AM|PM)$/, (_, m: string) => " " + m.toLowerCase());
}

const PUBLIC_SITES = "public price sites";

function mempoolReason(what: Problem, at: string, ctx: StatusContext): string {
  if (what === "mempool_untrusted_certificate") {
    return "Your Mempool's certificate isn't trusted (a private one, like StartOS's home-network address), so BitcoinTX can't use it.";
  }
  if (what === "mempool_missing") return "Mempool isn't installed on this server yet.";
  return `Your Mempool didn't answer at ${clock(at, ctx.timezone)}.`;
}

function mempoolFix(what: Problem, managed: boolean, backup: boolean): string {
  if (what === "mempool_untrusted_certificate") {
    return "There's no newer price: use its http:// or .onion address instead, or on StartOS choose My Mempool on this server.";
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

function mempoolLine(st: PriceStatus, ctx: StatusContext): StatusLine {
  const { last_ok: ok, last_problem: problem } = st;
  // Why your Mempool last failed, kept when the backup failed after it
  const mine = problem?.what.startsWith("mempool") ? problem : (st.last_mempool_problem ?? null);
  const reason = mine ? mempoolReason(mine.what, mine.at, ctx) : "Your Mempool didn't answer.";
  if (problem && newer(problem.at, ok?.at)) {
    if (problem === mine) return { tone: "warning", text: `${reason} ${mempoolFix(problem.what, st.managed, ctx.backup)}` };
    const at = clock(problem.at, ctx.timezone);
    const backup = problem.what === "tor_no_answer"
      ? `Public price sites didn't answer through Tor either, at ${at}. Is Tor running?`
      : `${capital(PUBLIC_SITES)} didn't answer either, at ${at}.`;
    return { tone: "warning", text: `${reason} ${backup}` };
  }
  if (ok && ok.from !== "mempool") {
    // #178: never "from your Mempool" while the backup gives the prices
    return { tone: "warning", text: `${reason} Public price sites answered instead at ${clock(ok.at, ctx.timezone)}.` };
  }
  if (ok) return { tone: "ok", text: `Newer prices from your Mempool. Last price ${clock(ok.at, ctx.timezone)}.` };
  return { tone: "idle", text: "Newer prices will come from your Mempool." };
}

function publicLine(st: PriceStatus, ctx: StatusContext): StatusLine {
  const { last_ok: ok, last_problem: problem } = st;
  const via = ctx.tor ? ", through Tor" : "";
  if (problem && newer(problem.at, ok?.at)) {
    const at = clock(problem.at, ctx.timezone);
    return problem.what === "tor_no_answer"
      ? { tone: "warning", text: `Public price sites didn't answer through Tor at ${at}. Is Tor running?` }
      : { tone: "warning", text: `Public price sites didn't answer at ${at}. BitcoinTX asks again in a few minutes.` };
  }
  if (ok) return { tone: "ok", text: `Newer prices from public price sites${via}. Last price ${clock(ok.at, ctx.timezone)}.` };
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
