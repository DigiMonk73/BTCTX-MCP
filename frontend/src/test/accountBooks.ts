// The account books the frontend tests read, as GET /api/accounts/ gives them
// (2.0 spec 5.9's order); new ids start at 100 (5.1). A test derives its book
// from these rather than defining one of its own.

function account(
  id: number,
  name: string,
  kind: AccountKind,
  currency: Currency,
  extra: Partial<LedgerAccount> = {},
): LedgerAccount {
  return { id, name, kind, currency, exchange_id: null, exchange: null, hidden: false, in_use: true, ...extra };
}

const EXCHANGE = { exchange_id: 1, exchange: "Exchange" };
const KRAKEN = { exchange_id: 2, exchange: "Kraken" };

/** A 1.x ledger: its six accounts. */
export const ONE_OF_EACH: AccountBook = [
  account(1, "Bank", "bank", "USD"),
  account(2, "Wallet", "wallet", "BTC"),
  account(3, "Exchange USD", "exchange", "USD", EXCHANGE),
  account(4, "Exchange BTC", "exchange", "BTC", EXCHANGE),
  account(5, "BTC Fees", "fee", "BTC"),
  account(6, "USD Fees", "fee", "USD"),
];

/** Two banks, three wallets (one hidden) and two exchanges, in the list's order. */
export const TWO_OF_EACH: AccountBook = [
  account(1, "Bank", "bank", "USD"),
  account(100, "Credit Union", "bank", "USD", { in_use: false }),
  account(2, "Wallet", "wallet", "BTC"),
  account(101, "Cold Storage", "wallet", "BTC"),
  account(104, "Old Wallet", "wallet", "BTC", { hidden: true }),
  account(3, "Exchange USD", "exchange", "USD", EXCHANGE),
  account(4, "Exchange BTC", "exchange", "BTC", EXCHANGE),
  account(102, "Kraken USD", "exchange", "USD", { ...KRAKEN, in_use: false }),
  account(103, "Kraken BTC", "exchange", "BTC", KRAKEN),
  account(5, "BTC Fees", "fee", "BTC"),
  account(6, "USD Fees", "fee", "USD"),
];

const NEW_NAMES: Record<number, Partial<LedgerAccount>> = {
  1: { name: "Checking" },
  2: { name: "Phone Wallet" },
  3: { name: "Coinbase USD", exchange: "Coinbase" },
  4: { name: "Coinbase BTC", exchange: "Coinbase" },
};

/** ONE_OF_EACH renamed: every answer must come from the id and kind, never a 1.x name. */
export const RENAMED: AccountBook = ONE_OF_EACH.map((row) => ({ ...row, ...NEW_NAMES[row.id] }));

/** An id a row may name that the book doesn't have (5.13's missing account). */
export const MISSING = 999;
