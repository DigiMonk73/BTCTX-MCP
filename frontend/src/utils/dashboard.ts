// The dashboard's figures worked out from the server's answers.
import { formatBtc, formatUsd, parseDecimal } from "./format";

/** One line of the Portfolio Overview: a bank, a wallet, or an exchange with its dollars and bitcoin side by side (5.13). */
export interface PortfolioRow {
  key: string; // "account-<id>" or "exchange-<exchange_id>": nicknames of an account and an exchange may match
  name: string; // the nickname: the account's, or the exchange's
  usd?: number;
  btc?: number;
}

/** The Portfolio Overview's rows, and the BTC held in all accounts. */
export interface AccountTotals {
  rows: PortfolioRow[];
  totalBtc: number;
}

export const NO_TOTALS: AccountTotals = { rows: [], totalBtc: 0 };

// Banks, then wallets, then exchanges (5.9's order); fee accounts are no one's holdings
const ROW_KINDS: readonly AccountKind[] = ["bank", "wallet", "exchange"];

/** Today's BTC price as the dashboard fetched it. `off` when the owner has
 * no price source or turned prices off; `problem` is the server's reason
 * when there is no price. */
export interface LivePrice {
  loading: boolean;
  value: number | null;
  off: boolean;
  problem?: string;
  /** A stored choice waits for the owner to confirm it (#145, 2.9): nothing is asked. */
  waiting?: boolean;
  /** No price source chosen yet. */
  unchosen?: boolean;
  /** The server's price settings are invalid: nothing is asked (not the owner's choice). */
  invalid?: boolean;
  /** Public sites are asked through a proxy (Tor). */
  throughTor?: boolean;
  /** Where the price came from ("mempool", "kraken"…) and when (UTC), from the server. */
  source?: string;
  at?: string;
}

/** Whether a price answer's reason is that the choice waits to be confirmed (the server's 503). */
export function waitingDetail(detail: unknown): boolean {
  return typeof detail === "string" && detail.startsWith("Confirm where BitcoinTX gets newer prices");
}

/** Why there's no live price, from the server's answer (backend/services/outbound.py,
 * refuse_public): waiting to confirm, not chosen yet, Nobody (503, by choice), no
 * public site reached through the proxy, Tor (502, services/bitcoin.py), or no answer
 * from the chosen source (502, or anything else: a site that answered with a refusal,
 * as Bitstamp does through Tor, #241, was reached). */
export type NoPrice = "waiting" | "unchosen" | "off" | "invalid" | "tor" | "none";

export function noPriceReason(status: number | undefined, detail: unknown): NoPrice {
  if (status === 502 && typeof detail === "string" && detail.includes("could be reached through the proxy")) return "tor";
  if (status !== 503) return "none";
  if (waitingDetail(detail)) return "waiting";
  if (typeof detail === "string" && detail.startsWith("This server's price settings aren't valid")) return "invalid";
  return typeof detail === "string" && detail.startsWith("Prices: not chosen yet") ? "unchosen" : "off";
}

/** The live price's place when there's none, in a word or two (never $0.00). */
export function noPriceWords(price: LivePrice): string {
  if (price.waiting) return "Confirm your choice";
  if (price.unchosen) return "Not chosen yet";
  return price.off || price.invalid ? "Offline" : "No answer";
}

function siteName(source: string): string {
  return `${source.charAt(0).toUpperCase()}${source.slice(1)}`;
}

/** "From your Mempool", "From public price sites (Kraken)": where a live price came from. */
export function priceSourceWords(source: string | undefined, throughTor = false): string | null {
  if (!source) return null;
  if (source === "mempool") return "From your Mempool";
  return `From public price sites (${siteName(source)}${throughTor ? ", through Tor" : ""})`;
}

/** The sidebar's short form, one line however narrow (#208): "Your Mempool", "Kraken, through Tor". */
export function priceSourceShort(source: string | undefined, throughTor = false): string | null {
  if (!source) return null;
  if (source === "mempool") return "Your Mempool";
  return `${siteName(source)}${throughTor ? ", through Tor" : ""}`;
}

/** The overview's rows and the BTC held. An unreadable balance and the fee accounts
 * are left out; so is a hidden account at zero (5.13), though a hidden one holding
 * anything stays. */
export function accountTotals(balances: AccountBalance[]): AccountTotals {
  const rows = new Map<string, PortfolioRow & { kind: AccountKind }>();
  let totalBtc = 0;
  for (const acc of balances) {
    const balance = parseDecimal(acc.balance);
    if (Number.isNaN(balance) || !ROW_KINDS.includes(acc.kind) || (acc.hidden && balance === 0)) continue;
    if (acc.currency === "BTC") totalBtc += balance;
    // An exchange's two accounts are one row, keyed by its exchange: never by a name
    const exchange = acc.kind === "exchange" && acc.exchange_id !== null;
    const key = exchange ? `exchange-${acc.exchange_id}` : `account-${acc.account_id}`;
    const row = rows.get(key) ?? { key, name: exchange ? (acc.exchange ?? acc.name) : acc.name, kind: acc.kind };
    if (acc.currency === "USD") row.usd = balance;
    else row.btc = balance;
    rows.set(key, row);
  }
  // Stable: the balances' order within a kind
  const ordered = [...rows.values()].sort((a, b) => ROW_KINDS.indexOf(a.kind) - ROW_KINDS.indexOf(b.kind));
  return { rows: ordered.map(({ key, name, usd, btc }) => ({ key, name, usd, btc })), totalBtc };
}

/** A row's figures: "$40.00", "0.50000000 BTC", or both joined by " · ". */
export function rowFigures(row: PortfolioRow): string {
  const parts = [];
  if (row.usd !== undefined) parts.push(formatUsd(row.usd));
  if (row.btc !== undefined) parts.push(formatBtc(row.btc));
  return parts.join(" · ");
}

/** The colour of a net figure: green for a gain, red for a loss, none at 0. */
export function gainClass(value: number): string {
  return value > 0 ? "text-gain" : value < 0 ? "text-loss" : "";
}
