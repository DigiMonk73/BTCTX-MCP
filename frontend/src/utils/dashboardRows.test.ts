// B8-2 (spec 5.13): the Portfolio Overview's rows by kind, from the balances
// route's kind, exchange and hidden (B8-1). Each bank and each wallet is a row;
// an exchange is one row with its dollars and its bitcoin side by side. A hidden
// account at zero and the fee accounts are left out, by kind; never by a name.
import { describe, expect, it } from "vitest";
import { accountTotals, rowFigures } from "./dashboard";
import { balancesFor, RENAMED, TWO_OF_EACH } from "../test/accountBooks";

const AMOUNTS: [number, string][] = [
  [1, "1000.00"], [100, "250.00"], [2, "0.50000000"], [101, "0.25000000"], [104, "0.00000000"],
  [3, "40.00"], [4, "0.10000000"], [102, "0.00"], [103, "0.05000000"], [5, "0.00020000"], [6, "3.00"],
];

const shown = (balances: AccountBalance[]) =>
  accountTotals(balances).rows.map((row) => [row.name, rowFigures(row)]);

describe("the Portfolio Overview's rows (5.13)", () => {
  it("lists each bank, each wallet and each exchange in 5.9's order, an exchange on one row", () => {
    expect(shown(balancesFor(TWO_OF_EACH, AMOUNTS))).toEqual([
      ["Bank", "$1,000.00"],
      ["Credit Union", "$250.00"],
      ["Wallet", "0.50000000 BTC"],
      ["Cold Storage", "0.25000000 BTC"],
      ["Exchange", "$40.00 · 0.10000000 BTC"],
      ["Kraken", "$0.00 · 0.05000000 BTC"],
    ]);
  });

  it("leaves out a hidden account at zero and the fee accounts; the BTC total is unchanged", () => {
    const totals = accountTotals(balancesFor(TWO_OF_EACH, AMOUNTS));
    expect(totals.rows.map((row) => row.name)).not.toContain("Old Wallet");
    expect(totals.rows.map((row) => row.name)).not.toContain("BTC Fees");
    expect(totals.rows.map((row) => row.name)).not.toContain("USD Fees");
    expect(totals.totalBtc).toBeCloseTo(0.9, 8);
  });

  it("keeps a hidden account that holds anything, after the other wallets", () => {
    const amounts = AMOUNTS.map(([id, amount]): [number, string] => [id, id === 104 ? "0.01000000" : amount]);
    const totals = accountTotals(balancesFor(TWO_OF_EACH, amounts));
    expect(totals.rows.map((row) => row.name).slice(2, 5)).toEqual(["Wallet", "Cold Storage", "Old Wallet"]);
    expect(totals.totalBtc).toBeCloseTo(0.91, 8);
  });

  it("leaves out a fee account by its kind, whatever its name", () => {
    const balances = balancesFor(RENAMED, [[1, "5.00"], [2, "0.20000000"], [5, "0.00010000"], [6, "1.00"]]);
    balances[2] = { ...balances[2], name: "Fees" };
    expect(shown(balances)).toEqual([["Checking", "$5.00"], ["Phone Wallet", "0.20000000 BTC"]]);
  });

  it("names an exchange by its exchange's nickname (RENAMED's Coinbase)", () => {
    expect(shown(balancesFor(RENAMED, [[3, "12.00"], [4, "0.30000000"]]))).toEqual([
      ["Coinbase", "$12.00 · 0.30000000 BTC"],
    ]);
  });

  it("gives the same rows whatever order the balances come in", () => {
    const byId = [...AMOUNTS].sort(([a], [b]) => a - b);
    expect(shown(balancesFor(TWO_OF_EACH, byId))).toEqual(shown(balancesFor(TWO_OF_EACH, AMOUNTS)));
  });

  it("leaves out a balance that won't parse, and keeps an exchange at $0", () => {
    const balances = balancesFor(TWO_OF_EACH, [[2, "0.50000000"], [102, "0.00"], [103, "0.00000000"]]);
    balances[0] = { ...balances[0], balance: NaN };
    expect(shown(balances)).toEqual([["Kraken", "$0.00 · 0.00000000 BTC"]]);
  });

  it("keys an account and an exchange apart when their nicknames match", () => {
    const book = TWO_OF_EACH.map((a) => (a.id === 101 ? { ...a, name: "Kraken" } : a));
    const keys = accountTotals(balancesFor(book, [[101, "0.10000000"], [103, "0.20000000"]])).rows.map((r) => r.key);
    expect(keys).toEqual(["account-101", "exchange-2"]);
  });
});
