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

/** A kind's line on Portfolio Overview, as 1.x has them (#674): its key is its total's in AccountTotals. */
export type BalanceLineKey = Exclude<keyof AccountTotals, "totalBtc">;

/** The line an account's balance adds to: a bank's and a wallet's by kind, an exchange's by currency. */
function lineOf(account: AccountBalance): BalanceLineKey {
  if (account.kind === "bank") return "bank";
  if (account.kind === "wallet") return "wallet";
  return account.currency === "USD" ? "exchangeUsd" : "exchangeBtc";
}

/** The totals of the account balances, by kind (2.0 spec 5.13), hidden
 * accounts included: they still hold what they hold. */
export function accountTotals(balances: AccountBalance[]): AccountTotals {
  const totals = { ...NO_TOTALS };
  for (const { account, balance } of readable(balances)) totals[lineOf(account)] += balance;
  totals.totalBtc = totals.wallet + totals.exchangeBtc;
  return totals;
}

/** One account listed under its kind's line: a bank, a wallet, or one exchange's dollars or bitcoin. */
export interface LineAccount {
  key: string;
  name: string;
  amount: number;
  hidden: boolean;
}

/** A kind's line: its total and the accounts that make it up. */
export interface BalanceLine {
  key: BalanceLineKey;
  label: string;
  currency: "USD" | "BTC";
  total: number;
  accounts: LineAccount[];
}

const LINES: [BalanceLineKey, string, BalanceLine["currency"]][] = [
  ["bank", "Bank (USD)", "USD"], ["exchangeUsd", "Exchange (USD)", "USD"],
  ["exchangeBtc", "Exchange (BTC)", "BTC"], ["wallet", "Wallet (BTC)", "BTC"],
];

/** An account as listed under its line: an exchange's by the exchange's name, its line naming the currency. */
function lineAccount({ account, balance }: { account: AccountBalance; balance: number }): LineAccount {
  const name = account.kind === "exchange" ? account.exchange ?? account.name : account.name;
  return { key: `account-${account.account_id}`, name, amount: balance, hidden: account.hidden };
}

/** Bank (USD), Exchange (USD), Exchange (BTC) and Wallet (BTC), each with its
 * total and its accounts by id, the fee accounts on none; a hidden account
 * holding nothing in its line's currency is left out of it (5.13). */
export function balanceLines(balances: AccountBalance[]): BalanceLine[] {
  const shown = [...readable(balances)].sort((a, b) => a.account.account_id - b.account.account_id);
  const totals = accountTotals(balances);
  return LINES.map(([key, label, currency]) => ({
    key, label, currency, total: totals[key],
    accounts: shown.filter(({ account }) => lineOf(account) === key).map(lineAccount)
      .filter((row) => !row.hidden || row.amount !== 0),
  }));
}

/** A line's caret: only when it has something to list, more than one
 * account or a hidden one still holding something (#674). With one account
 * of each kind there's none, and the card is 1.x's. */
export function listsAccounts(line: BalanceLine): boolean {
  return line.accounts.length > 1 || line.accounts.some((account) => account.hidden);
}

/** Where this device keeps which lines are open: alpha.1's key for its cards
 * (#356), so a choice made there carries over (readOpenLines). */
export const OPEN_LINES_KEY = "btctx.dashboard.openCards";

// alpha.1's Exchange card showed the exchanges' dollars and bitcoin: both their lines
const ALPHA_1_EXCHANGE: BalanceLineKey[] = ["exchangeUsd", "exchangeBtc"];

/** The open lines as stored, in the card's order: only the four lines
 * (alpha.1's cards read as theirs); none for nothing or anything else. */
export function readOpenLines(stored: string | null): BalanceLineKey[] {
  try {
    const parsed: unknown = JSON.parse(stored ?? "[]");
    if (!Array.isArray(parsed)) return [];
    const open = parsed.flatMap((value) => (value === "exchange" ? ALPHA_1_EXCHANGE : [value]));
    return LINES.map(([key]) => key).filter((key) => open.includes(key));
  } catch {
    return [];
  }
}

/** The open lines once `key` is opened or closed. */
export function openLinesAfter(open: BalanceLineKey[], key: BalanceLineKey): BalanceLineKey[] {
  return open.includes(key) ? open.filter((k) => k !== key) : [...open, key];
}

/** The colour of a net figure: green for a gain, red for a loss, none at 0. */
export function gainClass(value: number): string {
  return value > 0 ? "text-gain" : value < 0 ? "text-loss" : "";
}
