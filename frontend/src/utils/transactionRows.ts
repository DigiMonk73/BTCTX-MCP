// What a row of the Transactions list says about its accounts and its
// amounts, from the account book (2.0 spec 5.13): names as the book has
// them, an amount in its account's currency, never a fixed account number.
import { accountCurrency, accountName, exchangeName, isBtcAccount } from "./accounts";
import { formatBtc, formatUsd } from "./format";
import { sourceOrPurpose } from "./transactionList";

function nameOf(book: AccountBook, id: number | null): string {
  return id === null ? "N/A" : accountName(book, id);
}

/** The account a row is about: a deposit's, a withdrawal's, a transfer's
 * two, and a Buy's or a Sell's exchange by its name. */
export function rowAccounts(tx: ITransaction, book: AccountBook): string {
  const { type, from_account_id, to_account_id } = tx;
  switch (type) {
    case "Deposit":
      return nameOf(book, to_account_id);
    case "Withdrawal":
      return nameOf(book, from_account_id);
    case "Transfer":
      return `${nameOf(book, from_account_id)} → ${nameOf(book, to_account_id)}`;
    case "Buy":
      return to_account_id === null ? "N/A" : exchangeName(book, to_account_id);
    case "Sell":
      return from_account_id === null ? "N/A" : exchangeName(book, from_account_id);
    default:
      return "Unknown";
  }
}

/** A deposit's source, a withdrawal's purpose, or "Consolidation" for a
 * bitcoin account sent to itself, which records only its fee (#159): a
 * wallet's or an exchange's BTC account alike. */
export function rowNote(tx: ITransaction, book: AccountBook): string {
  const { type } = tx;
  if (type === "Deposit" || type === "Withdrawal") return sourceOrPurpose(tx);
  const from = tx.from_account_id ?? undefined;
  if (type === "Transfer" && from === tx.to_account_id && isBtcAccount(book, from)) {
    return "Consolidation";
  }
  return "";
}

/** "Coins chosen" on a row whose coins were chosen to leave a wallet (#711); else nothing. */
export function coinsChosenNote(tx: ITransaction): string {
  return tx.chosen_coins?.length ? "Coins chosen" : "";
}

const inDollars = (book: AccountBook, id: number | null) => accountCurrency(book, id ?? undefined) === "USD";

/** The asset that moved (signed, as the account sees it) and its USD value. */
export function rowAmounts(tx: ITransaction, book: AccountBook): { primary: string; secondary: string } {
  const { type, amount, cost_basis_usd, proceeds_usd, from_account_id, to_account_id } = tx;
  const minus = "−";
  switch (type) {
    case "Deposit":
      return inDollars(book, to_account_id)
        ? { primary: `+${formatUsd(amount)}`, secondary: "" }
        : { primary: `+${formatBtc(amount)}`, secondary: cost_basis_usd ? formatUsd(cost_basis_usd) : "" };
    case "Withdrawal":
      return inDollars(book, from_account_id)
        ? { primary: `${minus}${formatUsd(amount)}`, secondary: "" }
        : { primary: `${minus}${formatBtc(amount)}`, secondary: proceeds_usd ? formatUsd(proceeds_usd) : "" };
    case "Transfer":
      return { primary: inDollars(book, from_account_id) ? formatUsd(amount) : formatBtc(amount), secondary: "" };
    case "Buy":
      return { primary: `+${formatBtc(amount)}`, secondary: cost_basis_usd ? formatUsd(cost_basis_usd) : "" };
    case "Sell":
      return { primary: `${minus}${formatBtc(amount)}`, secondary: proceeds_usd ? formatUsd(proceeds_usd) : "" };
    default:
      return { primary: `${amount}`, secondary: "" };
  }
}
