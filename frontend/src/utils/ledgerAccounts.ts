// Settings' "Wallets, exchanges and banks" (spec 5.9): what its rows and texts
// say, worked out from the account book. Pure: no React, no api.
import { formatBtc, formatUsd, parseDecimal } from "./format";

export const KIND_LABEL: Record<AccountKind, string> = {
  bank: "Bank",
  wallet: "Wallet",
  exchange: "Exchange",
  fee: "Fee",
};

/** The section's rows: your accounts, hidden ones too, in the book's order (5.9); never the fee accounts. */
export function settingsAccounts(book: AccountBook): LedgerAccount[] {
  return book.filter((account) => account.kind !== "fee");
}

/** An account's balance in its currency ("$250.00", "0.25000000 BTC"); "" when the balances don't list it. */
export function balanceText(balances: AccountBalance[], account: LedgerAccount): string {
  const row = balances.find((balance) => balance.account_id === account.id);
  if (!row) return "";
  const amount = parseDecimal(row.balance);
  return account.currency === "USD" ? formatUsd(amount) : formatBtc(amount);
}
