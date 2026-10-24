// Account books as GET /api/accounts/ lists them (backend/services/account.py,
// `listed`), for the form's tests: a fresh install's one of each, and one
// with accounts numbered from 100 (2.0 spec 5.1), a hidden wallet and a
// second exchange.

type Shape = Pick<LedgerAccount, "id" | "name" | "kind" | "currency"> & Partial<LedgerAccount>;

function account(shape: Shape): LedgerAccount {
  // An exchange's 1099-DA switch is on unless turned off (5.9); no other account has one
  const sends_1099da = shape.kind === "exchange" ? true : null;
  return { exchange_id: null, exchange: null, sends_1099da, hidden: false, in_use: false, ...shape };
}

const FEES = [
  account({ id: 5, name: "BTC Fees", kind: "fee", currency: "BTC" }),
  account({ id: 6, name: "USD Fees", kind: "fee", currency: "USD" }),
];

/** A fresh install: Bank 1, Wallet 2, the Exchange's USD 3 and BTC 4, the fee accounts 5 and 6. */
export const ONE_OF_EACH: AccountBook = [
  account({ id: 1, name: "Bank", kind: "bank", currency: "USD" }),
  account({ id: 2, name: "Wallet", kind: "wallet", currency: "BTC" }),
  account({ id: 3, name: "Exchange USD", kind: "exchange", currency: "USD", exchange_id: 1, exchange: "Exchange" }),
  account({ id: 4, name: "Exchange BTC", kind: "exchange", currency: "BTC", exchange_id: 1, exchange: "Exchange" }),
  ...FEES,
];

/** One of each, renamed, plus a second bank (101), a second wallet (100), a
 * hidden wallet (104), a second exchange, Kraken (102 USD, 103 BTC), and a
 * hidden one, Closed (105 USD, 106 BTC). */
export const MANY: AccountBook = [
  account({ id: 1, name: "Checking", kind: "bank", currency: "USD" }),
  account({ id: 101, name: "Savings", kind: "bank", currency: "USD" }),
  account({ id: 2, name: "Sparrow", kind: "wallet", currency: "BTC" }),
  account({ id: 100, name: "Coldcard", kind: "wallet", currency: "BTC" }),
  account({ id: 104, name: "Old phone", kind: "wallet", currency: "BTC", hidden: true }),
  account({ id: 3, name: "River USD", kind: "exchange", currency: "USD", exchange_id: 1, exchange: "River" }),
  account({ id: 4, name: "River BTC", kind: "exchange", currency: "BTC", exchange_id: 1, exchange: "River" }),
  account({ id: 102, name: "Kraken USD", kind: "exchange", currency: "USD", exchange_id: 2, exchange: "Kraken" }),
  account({ id: 103, name: "Kraken BTC", kind: "exchange", currency: "BTC", exchange_id: 2, exchange: "Kraken" }),
  account({ id: 105, name: "Closed USD", kind: "exchange", currency: "USD", exchange_id: 3, exchange: "Closed",
    hidden: true }),
  account({ id: 106, name: "Closed BTC", kind: "exchange", currency: "BTC", exchange_id: 3, exchange: "Closed",
    hidden: true }),
  ...FEES,
];

/** An id no account has: a row saved before 0.9.2 into an account since deleted (5.13). */
export const MISSING_ID = 42;
