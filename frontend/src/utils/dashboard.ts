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
