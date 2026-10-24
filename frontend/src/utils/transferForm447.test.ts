// A dollar transfer's Amount (To) is what arrived (#447): the form saves it
// as the server keeps dollar transfers (amount = what arrived, the fee on
// top), the fee being From − To; a bitcoin transfer is unchanged.
import { describe, expect, it } from "vitest";
import { ONE_OF_EACH as book } from "../test/books";
import { buildTransactionPayload, mapTransactionToFormData } from "./transactionForm";
import { dollarTransferFee, transferAmountProblem } from "./transferAmounts";

function form(fields: Partial<TransactionFormData>): TransactionFormData {
  return { type: "Transfer", timestamp: "2025-03-01T12:00", fee: 0, ...fields } as TransactionFormData;
}

function saved(fields: Partial<ITransaction>): ITransaction {
  return { id: 1, type: "Transfer", timestamp: "2025-03-01T12:00:00Z", fee_amount: 0, cost_basis_usd: 0,
    proceeds_usd: 0, realized_gain_usd: 0, ...fields } as ITransaction;
}

// One of each: Bank 1, Wallet 2, the Exchange's USD 3 and BTC 4
const bankToExchange = { fromAccountId: 1, toAccountId: 3 } as const;

describe("a dollar transfer (#447)", () => {
  it("saves what arrived as its amount and From − To as its fee, whatever the Fee field held", () => {
    const body = buildTransactionPayload(form({ ...bankToExchange, amountFrom: 1000, amountTo: 990 }), book);
    expect(body).toMatchObject({
      type: "Transfer", from_account_id: 1, to_account_id: 3,
      amount: 990, fee_amount: 10, fee_currency: "USD",
    });
  });

  it("Exchange USD to Bank the same way", () => {
    const body = buildTransactionPayload(form({
      fromAccountId: 3, toAccountId: 1,
      amountFrom: "250.10", amountTo: "250.05",
    }), book);
    expect(body).toMatchObject({ from_account_id: 3, to_account_id: 1, amount: 250.05, fee_amount: 0.05 });
  });

  it("with nothing lost on the way, saves no fee", () => {
    const body = buildTransactionPayload(form({ ...bankToExchange, amountFrom: 2500, amountTo: 2500, fee: 7 }), book);
    expect(body).toMatchObject({ amount: 2500, fee_amount: 0 });
  });

  it("a fee is in whole cents, never a float's leftover", () => {
    expect(dollarTransferFee(1000.1, 990.05)).toBe(10.05);
    expect(dollarTransferFee(0.3, 0.1)).toBe(0.2);
    expect(dollarTransferFee(100, 100)).toBe(0);
  });

  it("one saved before opens as From = amount + fee, To = amount, and saves the same figures", () => {
    const old = saved({ from_account_id: 1, to_account_id: 3, amount: 1000, fee_amount: 10, fee_currency: "USD" });
    const shown = mapTransactionToFormData(old, book);
    expect(shown).toMatchObject({ ...bankToExchange, amountFrom: 1010, amountTo: 1000, fee: 10 });
    expect(buildTransactionPayload(shown, book)).toMatchObject({
      from_account_id: 1, to_account_id: 3, amount: 1000, fee_amount: 10, fee_currency: "USD",
    });
  });

  it("cents add up without a float's leftover when it opens", () => {
    const shown = mapTransactionToFormData(saved({ from_account_id: 3, to_account_id: 1, amount: 0.1, fee_amount: 0.2,
      fee_currency: "USD" }), book);
    expect([shown.amountFrom, shown.amountTo]).toEqual([0.3, 0.1]);
    expect(buildTransactionPayload(shown, book)).toMatchObject({ amount: 0.1, fee_amount: 0.2 });
  });

  it("a large one opens in cents too, so it saves as it was", () => {
    const shown = mapTransactionToFormData(saved({ from_account_id: 1, to_account_id: 3, amount: 46856753.87,
      fee_amount: 99.05, fee_currency: "USD" }), book);
    expect(shown.amountFrom).toBe(46856852.92);
    expect(transferAmountProblem(shown, book, "amountFrom")).toBeNull();
    expect(buildTransactionPayload(shown, book)).toMatchObject({ amount: 46856753.87, fee_amount: 99.05 });
  });

  it("one stored past the cent (before #298) opens to 8 places, and the form says so", () => {
    const shown = mapTransactionToFormData(saved({ from_account_id: 1, to_account_id: 3, amount: 100,
      fee_amount: 0.005, fee_currency: "USD" }), book);
    expect(shown.amountFrom).toBe(100.005);
    expect(transferAmountProblem(shown, book, "amountFrom")).toBe("A USD amount can have at most 2 decimal places.");
  });
});

describe("a bitcoin transfer is unchanged", () => {
  it("saves what left as its amount and the Fee field's From − To", () => {
    const body = buildTransactionPayload(form({
      fromAccountId: 4, toAccountId: 2,
      amountFrom: 0.5, amountTo: 0.4999, fee: "0.0001",
    }), book);
    expect(body).toMatchObject({ from_account_id: 4, to_account_id: 2, amount: 0.5, fee_amount: 0.0001,
      fee_currency: "BTC" });
  });

  it("opens as From = amount, To = amount − fee", () => {
    const shown = mapTransactionToFormData(saved({ from_account_id: 4, to_account_id: 2, amount: 0.5,
      fee_amount: 0.0001, fee_currency: "BTC" }), book);
    expect(shown).toMatchObject({ amountFrom: 0.5, amountTo: 0.4999 });
  });
});

describe("the form's checks, in words", () => {
  const wallet = { fromAccountId: 2, toAccountId: 4 } as const;

  it("Amount (To) above Amount (From) is refused, in dollars or bitcoin", () => {
    const words = "Amount (To) can't be more than Amount (From): it's what arrived, Amount (From) less the fee.";
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 990, amountTo: 1000 }, book, "amountTo")).toBe(words);
    expect(transferAmountProblem({ ...wallet, amountFrom: 0.5, amountTo: 0.6 }, book, "amountTo")).toBe(words);
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 1000, amountTo: 1000 }, book, "amountTo")).toBeNull();
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 1000, amountTo: 990 }, book, "amountTo")).toBeNull();
  });

  it("a dollar amount past the cent is refused, Amount (From) too (it isn't sent)", () => {
    const words = "A USD amount can have at most 2 decimal places.";
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 1000.005, amountTo: 990 }, book, "amountFrom"))
      .toBe(words);
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 1000, amountTo: 990.001 }, book, "amountTo"))
      .toBe(words);
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 1000.29, amountTo: 0.29 }, book, "amountFrom"))
      .toBeNull();
    expect(transferAmountProblem({ ...wallet, amountFrom: 0.00012345, amountTo: 0.0001 }, book, "amountFrom"))
      .toBeNull();
  });

  it("cents are cents however large the amount (a float's error isn't a decimal place)", () => {
    for (const amount of [134217728.02, 134217728.05, 987654321.99, 9999999999.99]) {
      expect(transferAmountProblem({ ...bankToExchange, amountFrom: amount, amountTo: 1 }, book, "amountFrom")).toBeNull();
    }
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 134217728.005, amountTo: 1 }, book, "amountFrom"))
      .toBe("A USD amount can have at most 2 decimal places.");
  });

  it("a dollar transfer's Amount (To) is the amount saved, so it must be more than 0", () => {
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 10, amountTo: 0 }, book, "amountTo"))
      .toBe("Amount (To) must be more than 0.");
    expect(transferAmountProblem({ ...bankToExchange, amountFrom: 10, amountTo: 0.01 }, book, "amountTo")).toBeNull();
  });

  it("a move within one bitcoin account still needs its fee (#159)", () => {
    expect(transferAmountProblem({ fromAccountId: 2, toAccountId: 2,
      amountFrom: 0.8, amountTo: 0.8 }, book, "amountTo")).toMatch(/records only its network fee/);
    expect(transferAmountProblem({ fromAccountId: 2, toAccountId: 2,
      amountFrom: 0.8, amountTo: 0.7999 }, book, "amountTo")).toBeNull();
  });
});
