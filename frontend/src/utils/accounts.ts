// The account book in the browser (spec 5.4): every question about an account,
// answered from GET /api/accounts/ by its id. Never by a fixed number, never by
// its nickname, which the owner can change (Rick, 2026-10-20).

/** External: everything outside BitcoinTX. Not in the book; a fixed id everywhere (5.4). */
export const EXTERNAL_ID = 99;

// The owner's own accounts; the fee accounts hold fee lines and are in no picker (5.1)
const OWN_KINDS: readonly AccountKind[] = ["bank", "wallet", "exchange"];

function find(book: AccountBook, id: number | undefined): LedgerAccount | undefined {
  return book.find((account) => account.id === id);
}

/** What a screen calls an account: its nickname; "External" for 99; "account N (missing)" for an id the book lacks. */
export function accountName(book: AccountBook, id: number): string {
  if (id === EXTERNAL_ID) return "External";
  const account = find(book, id);
  return account ? account.name : `account ${id} (missing)`;
}

/** An exchange account's exchange, by its nickname ("Kraken"); any other account by its own name. */
export function exchangeName(book: AccountBook, id: number): string {
  const account = find(book, id);
  if (account?.kind === "exchange" && account.exchange) return account.exchange;
  return accountName(book, id);
}

export function accountCurrency(book: AccountBook, id: number | undefined): Currency | undefined {
  return find(book, id)?.currency;
}

export function accountKind(book: AccountBook, id: number | undefined): AccountKind | undefined {
  return find(book, id)?.kind;
}

/** A bitcoin account (5.1): a wallet or an exchange's BTC account; never a fee account. */
export function isBtcAccount(book: AccountBook, id: number | undefined): boolean {
  const account = find(book, id);
  return account !== undefined && OWN_KINDS.includes(account.kind) && account.currency === "BTC";
}

/** The owner's accounts, hidden ones too (5.5: "Hidden accounts are still yours"), in the book's order. */
export function yours(book: AccountBook): number[] {
  return book.filter((account) => OWN_KINDS.includes(account.kind)).map((account) => account.id);
}
