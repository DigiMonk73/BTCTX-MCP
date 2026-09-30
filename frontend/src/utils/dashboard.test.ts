import { describe, expect, it } from "vitest";
import { accountTotals, gainClass } from "./dashboard";

const balance = (account_id: number, name: string, currency: string, value: number | string): AccountBalance => ({
  account_id, name, currency, balance: value,
});

describe("accountTotals", () => {
  it("shows each account and adds up the BTC, leaving out the fee accounts", () => {
    expect(accountTotals([
      balance(1, "Bank", "USD", "1500.25"),
      balance(2, "Wallet", "BTC", "0.50000000"),
      balance(3, "Exchange USD", "USD", 20),
      balance(4, "Exchange BTC", "BTC", "0.25000000"),
      balance(5, "BTC Fees", "BTC", "0.00010000"),
      balance(6, "USD Fees", "USD", "12.00"),
    ])).toEqual({ bank: 1500.25, exchangeUsd: 20, exchangeBtc: 0.25, wallet: 0.5, totalBtc: 0.75 });
  });

  it("skips a balance that isn't a number", () => {
    expect(accountTotals([balance(2, "Wallet", "BTC", NaN), balance(4, "Exchange BTC", "BTC", "0.1")]))
      .toEqual({ bank: 0, exchangeUsd: 0, exchangeBtc: 0.1, wallet: 0, totalBtc: 0.1 });
  });

  it("is all zero with no accounts", () => {
    expect(accountTotals([])).toEqual({ bank: 0, exchangeUsd: 0, exchangeBtc: 0, wallet: 0, totalBtc: 0 });
  });
});

describe("gainClass", () => {
  it("colours a gain and a loss, and not zero", () => {
    expect(gainClass(12.5)).toBe("text-gain");
    expect(gainClass(-0.01)).toBe("text-loss");
    expect(gainClass(0)).toBe("");
  });
});
