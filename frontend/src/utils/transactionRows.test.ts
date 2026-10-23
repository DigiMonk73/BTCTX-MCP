import { describe, expect, it } from "vitest";
import { MISSING, ONE_OF_EACH, RENAMED, TWO_OF_EACH } from "../test/accountBooks";
import { rowAccounts, rowAmounts, rowNote } from "./transactionRows";

const tx = (fields: Partial<ITransaction>): ITransaction => ({
  id: 1, type: "Deposit", timestamp: "2024-06-01T12:00:00Z", from_account_id: 99, to_account_id: 2, amount: 0.5,
  fee_amount: 0, fee_currency: "BTC", cost_basis_usd: 0, proceeds_usd: 0, realized_gain_usd: 0,
  ...fields,
} as ITransaction);

describe("a row's accounts, by name from the book (2.0 spec 5.13)", () => {
  it("names a deposit's, a withdrawal's and a transfer's accounts", () => {
    expect(rowAccounts(tx({ to_account_id: 101 }), TWO_OF_EACH)).toBe("Cold Storage");
    expect(rowAccounts(tx({ type: "Withdrawal", from_account_id: 100, to_account_id: 99 }), TWO_OF_EACH))
      .toBe("Credit Union");
    expect(rowAccounts(tx({ type: "Transfer", from_account_id: 2, to_account_id: 101 }), TWO_OF_EACH))
      .toBe("Wallet → Cold Storage");
  });

  it("a Buy and a Sell show their exchange's name", () => {
    expect(rowAccounts(tx({ type: "Buy", from_account_id: 1, to_account_id: 103 }), TWO_OF_EACH)).toBe("Kraken");
    expect(rowAccounts(tx({ type: "Buy", from_account_id: 3, to_account_id: 4 }), TWO_OF_EACH)).toBe("Exchange");
    expect(rowAccounts(tx({ type: "Sell", from_account_id: 103, to_account_id: 102 }), TWO_OF_EACH)).toBe("Kraken");
    expect(rowAccounts(tx({ type: "Sell", from_account_id: 4, to_account_id: 3 }), RENAMED)).toBe("Coinbase");
  });

  it("goes by id, never by a 1.x name: renamed accounts show their names", () => {
    expect(rowAccounts(tx({ to_account_id: 2 }), RENAMED)).toBe("Phone Wallet");
    expect(rowAccounts(tx({ type: "Transfer", from_account_id: 1, to_account_id: 3 }), RENAMED))
      .toBe("Checking → Coinbase USD");
  });

  it("a missing account as the server's book names it", () => {
    expect(rowAccounts(tx({ to_account_id: MISSING }), ONE_OF_EACH)).toBe(`account ${MISSING} (missing)`);
  });
});

describe("a row's note", () => {
  it('any bitcoin account to itself is "Consolidation", an exchange\'s too', () => {
    for (const id of [2, 4, 101, 103]) {
      expect(rowNote(tx({ type: "Transfer", from_account_id: id, to_account_id: id }), TWO_OF_EACH))
        .toBe("Consolidation");
    }
    expect(rowNote(tx({ type: "Transfer", from_account_id: 2, to_account_id: 2 }), RENAMED)).toBe("Consolidation");
  });

  it("a move between two accounts has none, nor a dollar account to itself", () => {
    expect(rowNote(tx({ type: "Transfer", from_account_id: 4, to_account_id: 103 }), TWO_OF_EACH)).toBe("");
    expect(rowNote(tx({ type: "Transfer", from_account_id: 1, to_account_id: 1 }), TWO_OF_EACH)).toBe("");
  });

  it("a deposit's source and a withdrawal's purpose, as before", () => {
    expect(rowNote(tx({ source: "Income" }), ONE_OF_EACH)).toBe("Income");
    expect(rowNote(tx({ type: "Withdrawal", from_account_id: 2, to_account_id: 99, purpose: "Spent" }), ONE_OF_EACH))
      .toBe("Spent");
  });
});

describe("a row's amounts in its account's currency", () => {
  it("dollars for a second bank's and an exchange's dollars, bitcoin for a second wallet", () => {
    expect(rowAmounts(tx({ to_account_id: 100, amount: 250 }), TWO_OF_EACH).primary).toBe("+$250.00");
    expect(rowAmounts(tx({ type: "Withdrawal", from_account_id: 102, to_account_id: 99, amount: 20 }), TWO_OF_EACH)
      .primary).toBe("−$20.00");
    expect(rowAmounts(tx({ type: "Transfer", from_account_id: 100, to_account_id: 1, amount: 75 }), TWO_OF_EACH)
      .primary).toBe("$75.00");
    expect(rowAmounts(tx({ to_account_id: 101, amount: 0.25, cost_basis_usd: 5000 }), TWO_OF_EACH))
      .toEqual({ primary: "+0.25000000 BTC", secondary: "$5,000.00" });
  });

  it("by currency, never by number: a renamed bank is still dollars", () => {
    expect(rowAmounts(tx({ to_account_id: 1, amount: 100 }), RENAMED).primary).toBe("+$100.00");
  });

  it("a Buy's and a Sell's bitcoin, with its dollars under it", () => {
    expect(rowAmounts(tx({ type: "Buy", from_account_id: 102, to_account_id: 103, amount: 0.1, cost_basis_usd: 6000 }),
      TWO_OF_EACH)).toEqual({ primary: "+0.10000000 BTC", secondary: "$6,000.00" });
  });
});
