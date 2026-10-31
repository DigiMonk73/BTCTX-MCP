// The account book in the browser (2.0 spec 5.4): every question about an
// account, answered from GET /api/accounts/ by its id. Never by a fixed
// number, never by its name, which the owner can change; and what each of
// the transaction form's pickers offers (5.5, 5.13).

/** External: everything outside BitcoinTX. In no book; the same id everywhere (5.4). */
export const EXTERNAL_ID = 99;

// The owner's own accounts; the fee accounts hold fee lines and are in no picker (5.1)
const YOUR_KINDS: readonly AccountKind[] = ["bank", "wallet", "exchange"];

const GROUP_LABELS: Record<string, string> = { bank: "Banks", wallet: "Wallets", exchange: "Exchanges" };

/** A picker's value as an id. A blank select holds "" (no account, 5.13):
 * every reader of a picker goes through this, so none takes "" for a choice. */
export function chosenId(value: unknown): number | undefined {
  if (value === "" || value == null) return undefined;
  const id = Number(value);
  return Number.isInteger(id) ? id : undefined;
}

function find(book: AccountBook, id: number | undefined): LedgerAccount | undefined {
  return book.find((account) => account.id === id);
}

/** What a screen calls an account: its name; "External" for 99; "account N (missing)" for an id the book lacks. */
export function accountName(book: AccountBook, id: number): string {
  if (id === EXTERNAL_ID) return "External";
  const account = find(book, id);
  return account ? account.name : `account ${id} (missing)`;
}

/** An exchange's account by its exchange's name ("Kraken"); any other by its own name. */
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

/** A bitcoin account (5.1): a wallet or an exchange's BTC account, never a fee account. */
export function isBtcAccount(book: AccountBook, id: number | undefined): boolean {
  const account = find(book, id);
  return account !== undefined && YOUR_KINDS.includes(account.kind) && account.currency === "BTC";
}

/** The owner's accounts, hidden ones too (5.5: "Hidden accounts are still yours"), in the book's order. */
export function yours(book: AccountBook): number[] {
  return book.filter((account) => YOUR_KINDS.includes(account.kind)).map((account) => account.id);
}

/** What a picker offers: the owner's accounts not hidden, and the row's own saved one if it's one of them. */
export function visibleAccounts(book: AccountBook, keepId?: number): number[] {
  return book
    .filter((account) => YOUR_KINDS.includes(account.kind) && (!account.hidden || account.id === keepId))
    .map((account) => account.id);
}

/**
 * Where a Transfer from `fromId` can go (5.5): the other accounts of its
 * currency, then itself, only for a bitcoin account (a consolidation, #159),
 * last as the form has always listed it. From External, a fee account or a
 * missing id, nowhere.
 */
export function transferTargets(book: AccountBook, fromId: number | undefined, keepId?: number): number[] {
  if (fromId === undefined || !yours(book).includes(fromId)) return [];
  const currency = accountCurrency(book, fromId);
  const others = visibleAccounts(book, keepId).filter((id) => id !== fromId && accountCurrency(book, id) === currency);
  return isBtcAccount(book, fromId) ? [...others, fromId] : others;
}

/** A Buy's or a Sell's exchange: every exchange's BTC account. */
export function buyExchanges(book: AccountBook, keepId?: number): number[] {
  return visibleAccounts(book, keepId).filter(
    (id) => accountKind(book, id) === "exchange" && accountCurrency(book, id) === "BTC",
  );
}

export const sellExchanges = buyExchanges;

/**
 * What pays for a Buy on the exchange whose BTC account is `exchangeId`
 * (5.5, Q15): that exchange's dollars, first, or a bank. Nothing before
 * the exchange is chosen, so a picker that fills the only account that fits
 * never fills a bank while the exchange is still blank.
 */
export function buyPayers(book: AccountBook, exchangeId: number | undefined, keepId?: number): number[] {
  if (accountKind(book, exchangeId) !== "exchange") return [];
  const visible = visibleAccounts(book, keepId);
  const dollars = usdOf(book, exchangeId);
  const banks = visible.filter((id) => accountKind(book, id) === "bank");
  return dollars !== undefined && visible.includes(dollars) ? [dollars, ...banks] : banks;
}

/** An exchange account's dollar half (5.4's usd_of); undefined for any other account. */
export function usdOf(book: AccountBook, id: number | undefined): number | undefined {
  return exchangeHalf(book, id, "USD");
}

/** An exchange account's bitcoin half (5.4's btc_of); undefined for any other account. */
export function btcOf(book: AccountBook, id: number | undefined): number | undefined {
  return exchangeHalf(book, id, "BTC");
}

// An exchange's two accounts share an exchange_id (5.4); nothing else has another half
function exchangeHalf(book: AccountBook, id: number | undefined, currency: Currency): number | undefined {
  const account = find(book, id);
  if (account?.kind !== "exchange" || account.exchange_id === null) return undefined;
  return book.find(
    (other) => other.kind === "exchange" && other.exchange_id === account.exchange_id && other.currency === currency,
  )?.id;
}

/** How many exchanges the book has, hidden ones too (an exchange is its two accounts). */
export function exchangeCount(book: AccountBook): number {
  return new Set(book.filter((account) => account.kind === "exchange").map((account) => account.exchange_id)).size;
}

/**
 * A picker's options by kind (P7's mockups: Banks, Wallets, Exchanges), in
 * the order they come, once they hold more than one kind and more than one
 * bank, wallet or exchange; else null: one of each lists them as 1.x did,
 * and a list of one kind has nothing to tell apart.
 */
export function byKind(book: AccountBook, ids: number[]): Array<{ label: string; ids: number[] }> | null {
  const groups = new Map<string, number[]>();
  for (const id of ids) {
    const kind = accountKind(book, id) ?? "";
    groups.set(kind, [...(groups.get(kind) ?? []), id]);
  }
  const places = (kind: string, members: number[]) =>
    kind === "exchange" ? new Set(members.map((id) => find(book, id)?.exchange_id)).size : members.length;
  if (groups.size < 2 || ![...groups].some(([kind, members]) => places(kind, members) > 1)) return null;
  return [...groups].map(([kind, members]) => ({ label: GROUP_LABELS[kind] ?? "Other", ids: members }));
}
