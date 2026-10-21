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

/** A Buy's "Paid from" (5.5): banks and exchanges' USD accounts. */
export function buyPayers(book: AccountBook, keepId?: number): number[] {
  return visibleAccounts(book, keepId).filter((id) => {
    const kind = accountKind(book, id);
    return (kind === "bank" || kind === "exchange") && accountCurrency(book, id) === "USD";
  });
}

/** A Buy's exchange: the paying exchange's BTC account when paid from an exchange's dollars (Q15), else every exchange's BTC account; none before a payer. */
export function buyExchanges(book: AccountBook, payerId: number | undefined, keepId?: number): number[] {
  // Nothing is offered until a payer is chosen. A wallet, External, a fee account and a missing id never pay (5.5).
  if (payerId === undefined || !buyPayers(book, payerId).includes(payerId)) return [];
  // An exchange's dollars buy only on that exchange (Q15). Its BTC half stays the answer even when that account is hidden.
  if (accountKind(book, payerId) === "exchange") {
    const half = btcOf(book, payerId);
    return half === undefined ? [] : [half];
  }
  return visibleAccounts(book, keepId).filter(
    (id) => accountKind(book, id) === "exchange" && accountCurrency(book, id) === "BTC",
  );
}

/** A Sell's exchange: the exchanges' BTC accounts. */
export function sellExchanges(book: AccountBook, keepId?: number): number[] {
  return visibleAccounts(book, keepId).filter(
    (id) => accountKind(book, id) === "exchange" && accountCurrency(book, id) === "BTC",
  );
}

/** An exchange account's other half (5.4's usd_of, btc_of); undefined for any other account. */
export function usdOf(book: AccountBook, id: number | undefined): number | undefined {
  return exchangeHalf(book, id, "USD");
}

/** An exchange account's other half (5.4's usd_of, btc_of); undefined for any other account. */
export function btcOf(book: AccountBook, id: number | undefined): number | undefined {
  return exchangeHalf(book, id, "BTC");
}

// An exchange's two accounts share an exchange_id (5.4). Anything else has no other half.
function exchangeHalf(book: AccountBook, id: number | undefined, currency: Currency): number | undefined {
  const account = find(book, id);
  if (account?.kind !== "exchange" || account.exchange_id === null) return undefined;
  const halves = book
    .filter(
      (other) =>
        other.kind === "exchange" &&
        other.exchange_id === account.exchange_id &&
        other.currency === currency,
    )
    .map((other) => other.id);
  return halves.length === 0 ? undefined : halves[0];
}
