// Choosing which coins leave one of your wallets (#711, step C3): the
// picker's pure logic. What leaves (a Transfer's Amount (From), its fee in
// it; a Withdrawal's amount and its fee), in exact satoshis; when a choice
// adds up; the two quick fills (Q3: oldest first always, highest cost first
// only on a transaction dated today); the words around it.
import { describe, expect, it } from "vitest";
import { MANY } from "../test/books";
import {
  CHOOSE_RULE, addsUp, choosable, chosenOn, droppedChoice, highestCostFirst, howAcquired, leaving, oldestFirst,
  runningTotal, sentLines, unreadable, type HeldLine,
} from "./chosenCoins";
import { coinsChosenNote } from "./transactionRows";

const line = (id: number, acquired: string, btc: string, cost: string, oldest: string, more: Partial<HeldLine> = {}):
  HeldLine => ({
  acquired_txn_id: id, kind: "Deposit", source: "MyBTC", account: "Sparrow", date: acquired, acquired,
  inherited: false, btc, cost_usd: cost, term: "LONG", oldest_first: oldest, ...more,
});
// Sparrow holds 0.3 BTC acquired 2017 ($1,000/BTC), 0.5 from 2025 ($90,000/BTC) and 0.2 from 2024 ($60,000/BTC)
const HELD = [
  line(11, "2017-03-01", "0.30000000", "300.00", "0.30000000"),
  line(12, "2024-05-01", "0.20000000", "12000.00", "0.10010000", { kind: "Buy", source: null, account: "River BTC" }),
  line(13, "2025-01-15", "0.50000000", "45000.00", "0.00000000", { term: "SHORT" }),
];
const spend = (amount: string, fee: string): TransactionFormData =>
  ({ type: "Withdrawal", timestamp: "2025-06-01T12:00", fromAccountId: 2, amount, fee, purpose: "Spent" });
const transfer = (from: string, to: string, toId = 100): TransactionFormData =>
  ({ type: "Transfer", timestamp: "2025-06-01T12:00", fromAccountId: 2, toAccountId: toId, amountFrom: from,
     amountTo: to, fee: 0 });

describe("where coins can be chosen", () => {
  it("a Transfer out of a wallet to another account, or a Withdrawal from a wallet", () => {
    expect(choosable(transfer("0.4", "0.4"), MANY)).toBe(true);
    expect(choosable(transfer("0.4", "0.4", 4), MANY)).toBe(true); // to an exchange
    expect(choosable(spend("0.1", "0"), MANY)).toBe(true);
  });

  it("never on an exchange's coins, a consolidation, dollars or another type", () => {
    expect(choosable({ ...transfer("0.4", "0.4"), fromAccountId: 4 }, MANY)).toBe(false); // River BTC
    expect(choosable(transfer("0.4", "0.3999", 2), MANY)).toBe(false); // within Sparrow
    expect(choosable({ ...spend("100", "0"), fromAccountId: 1 }, MANY)).toBe(false); // Checking
    expect(choosable({ ...spend("0.1", "0"), type: "Sell", fromAccountId: 4 }, MANY)).toBe(false);
  });
});

describe("what leaves, in satoshis", () => {
  it("a Withdrawal: its amount and its fee", () => {
    expect(leaving(spend("0.1", "0.0001"))).toEqual({ kind: "Withdrawal", total: 10010000, moved: 10000000, fee: 10000 });
  });

  it("a Transfer: Amount (From), which holds its fee, Amount (To) arriving", () => {
    expect(leaving(transfer("0.0101", "0.01"))).toEqual({ kind: "Transfer", total: 1010000, moved: 1000000, fee: 10000 });
  });
});

describe("a choice", () => {
  const leaves = leaving(spend("0.1", "0.0001"));

  it("adds up when its lines cover exactly what leaves", () => {
    expect(addsUp([{ acquired_txn_id: 13, btc: "0.1001" }], leaves)).toBe(true);
    expect(addsUp([{ acquired_txn_id: 11, btc: "0.00005" }, { acquired_txn_id: 13, btc: "0.10005" }], leaves)).toBe(true);
    expect(addsUp([{ acquired_txn_id: 13, btc: "0.1" }], leaves)).toBe(false);
    expect(addsUp([], leaves)).toBe(false);
  });

  it("is sent with its blank and 0 lines left out, each in eight places", () => {
    expect(sentLines([{ acquired_txn_id: 11, btc: "" }, { acquired_txn_id: 12, btc: "0" },
                      { acquired_txn_id: 13, btc: "0.1001" }])).toEqual([{ acquired_txn_id: 13, btc: "0.10010000" }]);
  });

  it("says its running total in the form's own terms", () => {
    const lines = [{ acquired_txn_id: 13, btc: "0.1" }];
    expect(runningTotal(lines, leaves)).toBe(
      "Chosen 0.10000000 of 0.10010000 BTC: the amount 0.10000000 and the network fee 0.00010000.");
    expect(runningTotal([{ acquired_txn_id: 13, btc: "0.0101" }], leaving(transfer("0.0101", "0.01")))).toBe(
      "Chosen 0.01010000 of 0.01010000 BTC: Amount (To) 0.01000000 and the network fee 0.00010000.");
    expect(runningTotal(lines, leaving(spend("0.1", "0")))).toBe("Chosen 0.10000000 of 0.10000000 BTC.");
  });
});

describe("the quick fills (Q3)", () => {
  it("oldest first: what the save takes without a choice", () => {
    expect(oldestFirst(HELD)).toEqual([{ acquired_txn_id: 11, btc: "0.30000000" },
                                       { acquired_txn_id: 12, btc: "0.10010000" }]);
  });

  it("highest cost first: the dearest coins a BTC first, the smallest gain", () => {
    expect(highestCostFirst(HELD, leaving(spend("0.6", "0.0001")))).toEqual([
      { acquired_txn_id: 13, btc: "0.50000000" }, { acquired_txn_id: 12, btc: "0.10010000" }]);
  });
});

describe("the words", () => {
  it("always say when a choice counts (Treas. Reg. §1.1012-1(j))", () => {
    expect(CHOOSE_RULE).toBe(
      "Choose coins only if you decided which coins to send by the time they left, and your records from then " +
      "show which purchases they were (a note you made, or coin control in your wallet with records tying its " +
      "coins to purchases). Otherwise the IRS counts the oldest coins as the ones that left (Treas. Reg. " +
      "§1.1012-1(j)). A tax professional can tell you whether your records are enough.");
  });

  it("say when a choice was made, and when that's after the coins left", () => {
    expect(chosenOn("2025-06-01T15:00:00Z", "2025-06-01T12:00:00Z")).toBe("Chosen on Jun 1, 2025.");
    expect(chosenOn("2025-07-04T15:00:00Z", "2025-06-01T12:00:00Z")).toBe(
      "Chosen on Jul 4, 2025, after the coins left on Jun 1, 2025. A choice counts only if you made it by then " +
      "and your records show it.");
  });

  it("say how and where coins were acquired", () => {
    expect(howAcquired(HELD[0])).toBe("My BTC · Sparrow · Mar 1, 2017");
    expect(howAcquired(HELD[1])).toBe("Buy · River BTC · May 1, 2024");
  });
});

describe("the Transactions list", () => {
  it("marks a row whose coins were chosen", () => {
    const tx = { id: 7, type: "Withdrawal", purpose: "Spent", from_account_id: 2, to_account_id: 99 } as ITransaction;
    expect(coinsChosenNote({ ...tx, chosen_coins: [{ acquired_txn_id: 13, btc: "0.10010000" }] })).toBe("Coins chosen");
    expect(coinsChosenNote({ ...tx, chosen_coins: null })).toBe("");
    expect(coinsChosenNote(tx)).toBe("");
  });
});

describe("what the form refuses or says", () => {
  it("a BTC field that isn't a plain number of at most 8 places (the review's)", () => {
    for (const btc of ["-0.1", "0.1.2", "1e-3", "0.123456789", "abc"]) {
      expect(unreadable([{ acquired_txn_id: 1, btc }])).toBe(true);
    }
    for (const btc of ["", "0.1", ".5", "2", "0.12345678", "1."]) {
      expect(unreadable([{ acquired_txn_id: 1, btc }])).toBe(false);
    }
  });

  it("a stored choice an edit will set back to oldest first (the review's)", () => {
    const saved = { chosenCoinsSaved: [{ acquired_txn_id: 13, btc: "0.10010000" }], coinsChosenAt: "2025-07-04T15:00:00Z" };
    const edit = { ...spend("0.1", "0.0001"), ...saved };
    expect(droppedChoice({ ...edit, chosenCoins: [{ acquired_txn_id: 13, btc: "0.1001" }] }, MANY)).toBeNull();
    expect(droppedChoice({ ...edit, chosenCoins: null }, MANY)).toBe(
      "The coins chosen on Jul 4, 2025 go back to oldest first when you save.");
    expect(droppedChoice({ ...edit, fromAccountId: 4, chosenCoins: [{ acquired_txn_id: 13, btc: "0.1001" }] }, MANY))
      .toBe("The coins chosen on Jul 4, 2025 go back to oldest first when you save.");
    expect(droppedChoice({ ...spend("0.1", "0"), chosenCoins: null }, MANY)).toBeNull();
  });
});
