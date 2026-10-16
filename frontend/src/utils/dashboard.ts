// The dashboard's figures worked out from the server's answers.
import { parseDecimal } from "./format";

/** The balances the Portfolio Overview shows, and the BTC held in all
 * accounts. */
export interface AccountTotals {
  bank: number;
  exchangeUsd: number;
  exchangeBtc: number;
  wallet: number;
  totalBtc: number;
}

export const NO_TOTALS: AccountTotals = { bank: 0, exchangeUsd: 0, exchangeBtc: 0, wallet: 0, totalBtc: 0 };

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

/** The totals of the account balances. Fee accounts and unreadable balances
 * are left out. */
export function accountTotals(balances: AccountBalance[]): AccountTotals {
  const totals = { ...NO_TOTALS };
  for (const acc of balances) {
    const balance = parseDecimal(acc.balance);
    if (Number.isNaN(balance) || acc.name === "BTC Fees" || acc.name === "USD Fees") continue;
    if (acc.name === "Bank" && acc.currency === "USD") totals.bank = balance;
    else if (acc.name === "Wallet" && acc.currency === "BTC") totals.wallet = balance;
    else if (acc.name === "Exchange USD" && acc.currency === "USD") totals.exchangeUsd = balance;
    else if (acc.name === "Exchange BTC" && acc.currency === "BTC") totals.exchangeBtc = balance;
    if (acc.currency === "BTC") totals.totalBtc += balance;
  }
  return totals;
}

/** The colour of a net figure: green for a gain, red for a loss, none at 0. */
export function gainClass(value: number): string {
  return value > 0 ? "text-gain" : value < 0 ? "text-loss" : "";
}
