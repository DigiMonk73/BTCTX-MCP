// Which coins a Transfer moves, shown before it saves (#706): asked only for
// a Transfer between two bitcoin accounts, with the body its Save sends, so
// the list and the save can't disagree; and the words around the list.
import { describe, expect, it } from "vitest";
import { MANY } from "../test/books";
import {
  acquiredText, coinsPayload, coinsUrl, feeLine, movesCoins, oldestFirstLine,
} from "./coinsMoved";
import { buildTransactionPayload } from "./transactionForm";

const SPARROW = 2, COLDCARD = 100, CHECKING = 1, SAVINGS = 101, KRAKEN_BTC = 103;

function transfer(more: Partial<TransactionFormData> = {}): TransactionFormData {
  return {
    type: "Transfer", timestamp: "2025-06-01T12:00", fromAccountId: SPARROW, toAccountId: COLDCARD,
    amountFrom: 0.4001, amountTo: 0.4, fee: "0.0001", ...more,
  } as TransactionFormData;
}

describe("which transfers move coins", () => {
  it("one between two bitcoin accounts", () => {
    expect(movesCoins(transfer(), MANY)).toBe(true);
    expect(movesCoins(transfer({ toAccountId: KRAKEN_BTC }), MANY)).toBe(true);
  });

  it("not a move within one wallet, which records only its fee (#159), nor dollars, which have no coins", () => {
    expect(movesCoins(transfer({ toAccountId: SPARROW }), MANY)).toBe(false);
    expect(movesCoins(transfer({ fromAccountId: CHECKING, toAccountId: SAVINGS }), MANY)).toBe(false);
  });

  it("not before both accounts are chosen, nor another type", () => {
    expect(movesCoins(transfer({ toAccountId: undefined }), MANY)).toBe(false);
    expect(movesCoins(transfer({ type: "Withdrawal" }), MANY)).toBe(false);
  });
});

describe("what's asked", () => {
  it("the body the Save sends", () => {
    expect(coinsPayload(transfer(), MANY)).toEqual(buildTransactionPayload(transfer(), MANY));
  });

  it("nothing until the amounts and the date are there", () => {
    expect(coinsPayload(transfer({ amountTo: undefined }), MANY)).toBeNull();
    expect(coinsPayload(transfer({ amountTo: 0 }), MANY)).toBeNull();
    expect(coinsPayload(transfer({ amountFrom: NaN }), MANY)).toBeNull();
    expect(coinsPayload(transfer({ amountTo: 0.5 }), MANY)).toBeNull(); // more arrived than left
    expect(coinsPayload(transfer({ timestamp: "" }), MANY)).toBeNull();
    expect(coinsPayload(transfer({ toAccountId: SPARROW }), MANY)).toBeNull();
  });

  it("a new transfer's, or an edit's", () => {
    expect(coinsUrl(undefined)).toBe("/transactions/coins-moved");
    expect(coinsUrl(null)).toBe("/transactions/coins-moved");
    expect(coinsUrl(7)).toBe("/transactions/7/coins-moved");
  });
});

describe("the words", () => {
  it("the oldest coins in the From account go first", () => {
    expect(oldestFirstLine(MANY, SPARROW)).toBe(
      "Moves your oldest coins in Sparrow first (first in, first out, the IRS default).");
  });

  it("the fee, when there is one", () => {
    expect(feeLine("0.00010000")).toBe(
      "The network fee, 0.0001 BTC, is paid first, from your oldest coins: a disposal at the fee's value, on " +
      "Form 8949.");
    expect(feeLine("0.00000000")).toBeNull();
    expect(feeLine(null)).toBeNull();
  });

  it("a date acquired as a date, never moved by a timezone (#185)", () => {
    expect(acquiredText({ acquired: "2017-03-01", btc: "0.3", cost_usd: "300.00", inherited: false }))
      .toBe("Mar 1, 2017");
    expect(acquiredText({ acquired: "2021-12-01", btc: "0.01", cost_usd: "400.00", inherited: true }))
      .toBe("Dec 1, 2021 (inherited)");
  });
});
