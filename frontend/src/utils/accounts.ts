// The account book in the browser (2.0 spec 5.4): every question about an
// account, answered from GET /api/accounts/ by its id. Never by a fixed number,
// never by its name, which the owner can change (5.9's Rename).

/** External: everything outside BitcoinTX. Not in the book; a fixed id everywhere (5.4). */
export const EXTERNAL_ID = 99;

// Your accounts; the fee accounts hold fee lines and are in no picker (5.1)
const YOUR_KINDS: readonly AccountKind[] = ["bank", "wallet", "exchange"];

function find(book: AccountBook, id: number | null | undefined): LedgerAccount | undefined {
  return book.find((account) => account.id === id);
}

/** What a screen calls an account, as the server's book does: its name;
 * "External" for 99; "account N (missing)" for an id the book lacks. */
export function accountName(book: AccountBook, id: number): string {
  if (id === EXTERNAL_ID) return "External";
  const account = find(book, id);
  return account ? account.name : `account ${id} (missing)`;
}

/** An exchange account's exchange, by its name ("Kraken"); any other account by its own name. */
export function exchangeName(book: AccountBook, id: number): string {
  const account = find(book, id);
  if (account?.kind === "exchange" && account.exchange) return account.exchange;
  return accountName(book, id);
}

export function accountCurrency(book: AccountBook, id: number | null | undefined): Currency | undefined {
  return find(book, id)?.currency;
}

export function accountKind(book: AccountBook, id: number | null | undefined): AccountKind | undefined {
  return find(book, id)?.kind;
}

/** A bitcoin account (5.1): a wallet or an exchange's BTC account; never a fee account. */
export function isBtcAccount(book: AccountBook, id: number | null | undefined): boolean {
  const account = find(book, id);
  return account !== undefined && YOUR_KINDS.includes(account.kind) && account.currency === "BTC";
}

/** Your accounts' ids, hidden ones too (5.4's yours()), in the book's order. */
export function yours(book: AccountBook): number[] {
  return book.filter((account) => YOUR_KINDS.includes(account.kind)).map((account) => account.id);
}
