import { describe, expect, it } from "vitest";
import { MANY, MISSING_ID, ONE_OF_EACH } from "../test/books";
import { rowAccounts, rowAmounts, rowNote } from "./transactionRows";

const tx = (fields: Partial<ITransaction>): ITransaction => ({
  id: 1, type: "Deposit", timestamp: "2024-06-01T12:00:00Z", from_account_id: 99, to_account_id: 2, amount: 0.5,
  fee_amount: 0, fee_currency: "BTC", cost_basis_usd: 0, proceeds_usd: 0, realized_gain_usd: 0,
  ...fields,
} as ITransaction);

describe("a row's accounts, by name from the book (2.0 spec 5.13)", () => {
  it("names a deposit's, a withdrawal's and a transfer's accounts", () => {
    expect(rowAccounts(tx({ to_account_id: 100 }), MANY)).toBe("Coldcard");
    expect(rowAccounts(tx({ type: "Withdrawal", from_account_id: 101, to_account_id: 99 }), MANY)).toBe("Savings");
    expect(rowAccounts(tx({ type: "Transfer", from_account_id: 2, to_account_id: 100 }), MANY))
      .toBe("Sparrow → Coldcard");
  });

  it("a Buy and a Sell show their exchange's name", () => {
    expect(rowAccounts(tx({ type: "Buy", from_account_id: 1, to_account_id: 103 }), MANY)).toBe("Kraken");
    expect(rowAccounts(tx({ type: "Buy", from_account_id: 3, to_account_id: 4 }), MANY)).toBe("River");
    expect(rowAccounts(tx({ type: "Sell", from_account_id: 103, to_account_id: 102 }), MANY)).toBe("Kraken");
    expect(rowAccounts(tx({ type: "Sell", from_account_id: 4, to_account_id: 3 }), ONE_OF_EACH)).toBe("Exchange");
  });

  it("goes by id, never by a 1.x name: renamed accounts show their names", () => {
    expect(rowAccounts(tx({ to_account_id: 2 }), MANY)).toBe("Sparrow");
    expect(rowAccounts(tx({ type: "Transfer", from_account_id: 1, to_account_id: 3 }), MANY))
      .toBe("Checking → River USD");
  });

  it("a missing account as the server's book names it", () => {
    expect(rowAccounts(tx({ to_account_id: MISSING_ID }), ONE_OF_EACH)).toBe(`account ${MISSING_ID} (missing)`);
  });
});

describe("a row's note", () => {
  it('any bitcoin account to itself is "Consolidation", an exchange\'s too', () => {
    for (const id of [2, 4, 100, 103]) {
      expect(rowNote(tx({ type: "Transfer", from_account_id: id, to_account_id: id }), MANY)).toBe("Consolidation");
    }
    expect(rowNote(tx({ type: "Transfer", from_account_id: 4, to_account_id: 4 }), ONE_OF_EACH)).toBe("Consolidation");
  });

  it("a move between two accounts has none, nor a dollar account to itself", () => {
    expect(rowNote(tx({ type: "Transfer", from_account_id: 4, to_account_id: 103 }), MANY)).toBe("");
    expect(rowNote(tx({ type: "Transfer", from_account_id: 1, to_account_id: 1 }), MANY)).toBe("");
  });

  it("a deposit's source and a withdrawal's purpose, as before", () => {
    expect(rowNote(tx({ source: "Income" }), ONE_OF_EACH)).toBe("Income");
    expect(rowNote(tx({ type: "Withdrawal", from_account_id: 2, to_account_id: 99, purpose: "Spent" }), ONE_OF_EACH))
      .toBe("Spent");
  });
});

describe("a row's amounts in its account's currency", () => {
  it("dollars for a second bank's and an exchange's dollars, bitcoin for a second wallet", () => {
    expect(rowAmounts(tx({ to_account_id: 101, amount: 250 }), MANY).primary).toBe("+$250.00");
    expect(rowAmounts(tx({ type: "Withdrawal", from_account_id: 102, to_account_id: 99, amount: 20 }), MANY)
      .primary).toBe("−$20.00");
    expect(rowAmounts(tx({ type: "Transfer", from_account_id: 101, to_account_id: 1, amount: 75 }), MANY)
      .primary).toBe("$75.00");
    expect(rowAmounts(tx({ to_account_id: 100, amount: 0.25, cost_basis_usd: 5000 }), MANY))
      .toEqual({ primary: "+0.25000000 BTC", secondary: "$5,000.00" });
  });

  it("by currency, never by number: a renamed bank is still dollars", () => {
    expect(rowAmounts(tx({ to_account_id: 1, amount: 100 }), MANY).primary).toBe("+$100.00");
  });

  it("a Buy's and a Sell's bitcoin, with its dollars under it", () => {
    expect(rowAmounts(tx({ type: "Buy", from_account_id: 102, to_account_id: 103, amount: 0.1, cost_basis_usd: 6000 }),
      MANY)).toEqual({ primary: "+0.10000000 BTC", secondary: "$6,000.00" });
  });
});
