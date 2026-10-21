// The account books every frontend test reads (P-3), as GET /api/accounts/ gives
// them (spec 5.9's order). `name` is the owner's nickname (Rick, 2026-10-20);
// new ids start at 100 (5.1). No test defines a book of its own: it derives one.

function account(
  id: number,
  name: string,
  kind: AccountKind,
  currency: Currency,
  extra: Partial<LedgerAccount> = {},
): LedgerAccount {
  const sends = kind === "exchange" ? { sends_1099da: true } : { sends_1099da: null };
  return { id, name, kind, currency, exchange_id: null, exchange: null, ...sends, hidden: false, in_use: true, ...extra };
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

const NICKNAMES: Record<number, Partial<LedgerAccount>> = {
  1: { name: "Checking" },
  2: { name: "Phone Wallet" },
  3: { name: "Coinbase USD", exchange: "Coinbase" },
  4: { name: "Coinbase BTC", exchange: "Coinbase" },
};

/** ONE_OF_EACH after the owner gave nicknames: every answer must come from the id and kind, never a 1.x name. */
export const RENAMED: AccountBook = ONE_OF_EACH.map((row) => ({ ...row, ...NICKNAMES[row.id] }));

/** An id a row may name that the book doesn't have (5.13's "missing account"). */
export const MISSING = 999;

/** GET /calculations/accounts/balances for `book`: one row per account listed in
 * `amounts` (id → the amount as the API sends it, a string), in the order given. */
export function balancesFor(book: AccountBook, amounts: [number, string][]): AccountBalance[] {
  return amounts.map(([id, balance]) => {
    const row = book.find((a) => a.id === id) as LedgerAccount;
    const { name, currency, kind, exchange_id, exchange, hidden } = row;
    return { account_id: id, name, currency, balance, kind, exchange_id, exchange, hidden };
  });
}

/** GET /calculations/accounts/balances for TWO_OF_EACH (B7b): one row per account,
 * the amounts as the API sends them (strings). */
export const TWO_BALANCES: AccountBalance[] = balancesFor(TWO_OF_EACH, [
  [1, "1000.00"], [100, "250.00"], [2, "0.50000000"], [101, "0.25000000"], [104, "0.00000000"],
  [3, "1200.50"], [4, "0.10000000"], [102, "0.00"], [103, "0.05000000"], [5, "0.00020000"], [6, "3.00"],
]);
