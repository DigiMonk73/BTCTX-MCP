// The dashboard's figures worked out from the server's answers.
import { parseDecimal } from "./format";

/** Each kind's balances, added up over its accounts, and the BTC held in
 * all of them. */
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

/** Your accounts' balances that can be read: a bank's, a wallet's, an
 * exchange's two; never a fee account's (by kind, whatever its name), nor
 * an unreadable one. */
function readable(balances: AccountBalance[]): { account: AccountBalance; balance: number }[] {
  return balances
    .filter((account) => account.kind === "bank" || account.kind === "wallet" || account.kind === "exchange")
    .map((account) => ({ account, balance: parseDecimal(account.balance) }))
    .filter(({ balance }) => !Number.isNaN(balance));
}

/** The totals of the account balances, by kind (2.0 spec 5.13), hidden
 * accounts included: they still hold what they hold. */
export function accountTotals(balances: AccountBalance[]): AccountTotals {
  const totals = { ...NO_TOTALS };
  for (const { account, balance } of readable(balances)) {
    if (account.kind === "bank") totals.bank += balance;
    else if (account.kind === "wallet") totals.wallet += balance;
    else if (account.currency === "USD") totals.exchangeUsd += balance;
    else totals.exchangeBtc += balance;
  }
  totals.totalBtc = totals.wallet + totals.exchangeBtc;
  return totals;
}

export type CardKind = "bank" | "exchange" | "wallet";

/** One line of a card's list: a bank or a wallet, or an exchange with its
 * dollars and its bitcoin side by side. */
export interface CardRow {
  key: string;
  name: string;
  usd: number;
  btc: number;
  hidden: boolean;
}

/** One of the dashboard's three cards: a kind's totals and its accounts. */
export interface KindCard {
  kind: CardKind;
  title: "Bank" | "Exchange" | "Wallet";
  usd: number;
  btc: number;
  rows: CardRow[];
}

const CARDS: [CardKind, KindCard["title"]][] = [["bank", "Bank"], ["exchange", "Exchange"], ["wallet", "Wallet"]];

/** The rows of one kind: an exchange's two accounts as one row, in the
 * balances' order (by id); a hidden one holding nothing left out (5.13). */
function cardRows(kind: CardKind, balances: { account: AccountBalance; balance: number }[]): CardRow[] {
  const rows = new Map<string, CardRow>();
  for (const { account, balance } of balances) {
    if (account.kind !== kind) continue;
    const isExchange = kind === "exchange" && account.exchange_id !== null;
    const key = isExchange ? `exchange-${account.exchange_id}` : `account-${account.account_id}`;
    const row = rows.get(key)
      ?? { key, name: isExchange ? account.exchange ?? account.name : account.name, usd: 0, btc: 0, hidden: true };
    if (account.currency === "USD") row.usd += balance;
    else row.btc += balance;
    row.hidden = row.hidden && account.hidden;
    rows.set(key, row);
  }
  return [...rows.values()].filter((row) => !row.hidden || row.usd !== 0 || row.btc !== 0);
}

/** Bank, Exchange and Wallet, as P7's mockups have them (#356): each with its
 * totals and its accounts, the fee accounts on none. */
export function kindCards(balances: AccountBalance[]): KindCard[] {
  const shown = [...readable(balances)].sort((a, b) => a.account.account_id - b.account.account_id);
  const totals = accountTotals(balances);
  const sums: Record<CardKind, [number, number]> = {
    bank: [totals.bank, 0], exchange: [totals.exchangeUsd, totals.exchangeBtc], wallet: [0, totals.wallet],
  };
  return CARDS.map(([kind, title]) => ({ kind, title, usd: sums[kind][0], btc: sums[kind][1], rows: cardRows(kind, shown) }));
}

/** The card's toggle: only when it has more than one account to show. */
export function toggleLabel(card: KindCard, open: boolean): string | null {
  if (card.rows.length < 2) return null;
  return open ? "Hide accounts" : `Show accounts (${card.rows.length})`;
}

/** Where the browser keeps which cards are open (P7: remembered per browser). */
export const OPEN_CARDS_KEY = "btctx.dashboard.openCards";

/** The open cards as stored: only the three kinds; none for nothing or anything else. */
export function readOpenCards(stored: string | null): CardKind[] {
  try {
    const parsed: unknown = JSON.parse(stored ?? "[]");
    return Array.isArray(parsed) ? CARDS.map(([kind]) => kind).filter((kind) => parsed.includes(kind)) : [];
  } catch {
    return [];
  }
}

/** The open cards once `kind` is opened or closed. */
export function openCardsAfter(open: CardKind[], kind: CardKind): CardKind[] {
  return open.includes(kind) ? open.filter((k) => k !== kind) : [...open, kind];
}

/** The colour of a net figure: green for a gain, red for a loss, none at 0. */
export function gainClass(value: number): string {
  return value > 0 ? "text-gain" : value < 0 ? "text-loss" : "";
}
