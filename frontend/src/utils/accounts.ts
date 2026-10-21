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

/** What a picker offers: the owner's accounts not hidden, plus the row's own saved one if it's one of them. */
export function visibleAccounts(book: AccountBook, keepId?: number): number[] {
  // A fee keepId is never added: it isn't one of the owner's accounts (5.1).
  return book
    .filter((account) => OWN_KINDS.includes(account.kind) && (!account.hidden || account.id === keepId))
    .map((account) => account.id);
}

/** Where a Transfer from `fromId` can go (5.5): visible accounts in its currency; itself only for a bitcoin account. */
export function transferTargets(book: AccountBook, fromId: number | undefined, keepId?: number): number[] {
  // A transfer starts from one of the owner's accounts. External, a fee account and a missing id have nowhere to go.
  if (fromId === undefined || !yours(book).includes(fromId)) return [];
  const currency = accountCurrency(book, fromId);
  // A dollar account never targets itself; a bitcoin account may, as a consolidation (#159).
  return visibleAccounts(book, keepId).filter(
    (id) => accountCurrency(book, id) === currency && (id !== fromId || isBtcAccount(book, fromId)),
  );
}
