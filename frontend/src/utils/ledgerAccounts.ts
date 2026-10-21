// Settings' "Wallets, exchanges and banks" (spec 5.9): what its rows and texts
// say, worked out from the account book. Pure: no React, no api.
import axios from "axios";
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

/** The kinds the owner adds (5.1): never a fee account. */
export type YourKind = "bank" | "wallet" | "exchange";

const WALLET_HELP =
  "A wallet is one set of keys: every address it makes is part of it. A backup of the same keys (a seed phrase, " +
  "or another device with the same keys) isn't a second wallet. If you use multiple wallets, add each one: since " +
  "2025 the IRS figures cost basis wallet by wallet.";

const POOLED_NOTE: Record<"wallet" | "exchange", string> = {
  wallet:
    "Years before you add this wallet were figured with your wallets together, as BitcoinTX 1.x did. Move coins " +
    "into it with a Transfer dated when they really moved: BitcoinTX moves the oldest coins first. A Transfer dated " +
    "in an earlier year can change that year's figures and later ones (BitcoinTX shows which years before it " +
    "saves), and BitcoinTX doesn't allocate your cost basis to each wallet as of January 1, 2025 (Rev. Proc. " +
    "2024-28). A tax professional can tell you whether an earlier return needs a change.",
  exchange:
    "Years before you add this exchange were figured with your exchange accounts together, as BitcoinTX 1.x did. " +
    "Move coins into it with a Transfer dated when they really moved: BitcoinTX moves the oldest coins first. A " +
    "Transfer dated in an earlier year can change that year's figures and later ones (BitcoinTX shows which years " +
    "before it saves), and BitcoinTX doesn't allocate your cost basis to each exchange account as of January 1, " +
    "2025 (Rev. Proc. 2024-28). A tax professional can tell you whether an earlier return needs a change.",
};

/** The help text under the Nickname field when adding (5.1, 5.9), word for word; none for a bank. */
export function addHelp(kind: YourKind, name: string): string | null {
  if (kind === "wallet") return WALLET_HELP;
  if (kind === "bank") return null;
  const shown = name.trim() || "name";
  return `BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, '${shown} USD' and '${shown} BTC'.`;
}

/** Q5's note (5.8) when adding a second wallet or exchange while one of that kind is in use; else null. */
export function pooledNote(book: AccountBook, kind: YourKind): string | null {
  if (kind === "bank") return null;
  return book.some((account) => account.kind === kind && account.in_use) ? POOLED_NOTE[kind] : null;
}

/** The past-year warning's fingerprint (5.8; B6c's stub): a 409 whose body carries
 * `confirm` asks the owner first. Null for any other refusal or error. */
export function pastYearsConfirm(error: unknown): string | null {
  if (!axios.isAxiosError(error) || error.response?.status !== 409) return null;
  const confirm: unknown = error.response?.data?.confirm;
  return typeof confirm === "string" ? confirm : null;
}
