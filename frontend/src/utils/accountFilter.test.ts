import { describe, expect, it } from "vitest";
import { MANY, ONE_OF_EACH } from "../test/books";
import { ALL_ACCOUNTS, filterCount, filterGroups, matchesFilter } from "./accountFilter";

const tx = (from_account_id: number, to_account_id: number) => ({ from_account_id, to_account_id });

describe("the account filter's choices, grouped by kind (P7's mockups, #356)", () => {
  it("each kind's accounts after its 'All', exchanges by exchange, hidden ones marked, names from the book", () => {
    expect(filterGroups(MANY)).toEqual([
      { label: "Wallets", options: [
        { value: "kind:wallet", label: "All wallets" }, { value: "account:2", label: "Sparrow" },
        { value: "account:100", label: "Coldcard" }, { value: "account:104", label: "Old phone (hidden)" }] },
      { label: "Exchanges", options: [
        { value: "kind:exchange", label: "All exchanges" }, { value: "exchange:1", label: "River" },
        { value: "exchange:2", label: "Kraken" }, { value: "exchange:3", label: "Closed (hidden)" }] },
      { label: "Banks", options: [
        { value: "kind:bank", label: "All banks" }, { value: "account:1", label: "Checking" },
        { value: "account:101", label: "Savings" }] },
    ]);
  });

  it("with one of a kind, no 'All' for it; the fee accounts never", () => {
    expect(filterGroups(ONE_OF_EACH)).toEqual([
      { label: "Wallets", options: [{ value: "account:2", label: "Wallet" }] },
      { label: "Exchanges", options: [{ value: "exchange:1", label: "Exchange" }] },
      { label: "Banks", options: [{ value: "account:1", label: "Bank" }] },
    ]);
  });
});

describe("which rows a choice keeps", () => {
  const rows = [tx(99, 2), tx(2, 100), tx(1, 4), tx(103, 102), tx(101, 99), tx(4, 4)];

  it("all accounts keeps every row", () => {
    expect(rows.filter((r) => matchesFilter(r, ALL_ACCOUNTS, MANY))).toHaveLength(6);
  });

  it("an account keeps the rows naming it on either side: a transfer shows under both", () => {
    expect(rows.filter((r) => matchesFilter(r, "account:100", MANY))).toEqual([tx(2, 100)]);
    expect(rows.filter((r) => matchesFilter(r, "account:2", MANY))).toEqual([tx(99, 2), tx(2, 100)]);
  });

  it("an exchange keeps both its accounts' rows", () => {
    expect(rows.filter((r) => matchesFilter(r, "exchange:2", MANY))).toEqual([tx(103, 102)]);
    expect(rows.filter((r) => matchesFilter(r, "exchange:1", MANY))).toEqual([tx(1, 4), tx(4, 4)]);
  });

  it("a kind keeps every row naming one of its accounts", () => {
    expect(rows.filter((r) => matchesFilter(r, "kind:wallet", MANY))).toEqual([tx(99, 2), tx(2, 100)]);
    expect(rows.filter((r) => matchesFilter(r, "kind:bank", MANY))).toEqual([tx(1, 4), tx(101, 99)]);
  });

  it("a choice that no longer means an account keeps nothing", () => {
    expect(rows.filter((r) => matchesFilter(r, "account:9999", MANY))).toEqual([]);
    expect(rows.filter((r) => matchesFilter(r, "nonsense", MANY))).toEqual([]);
  });

  it("says how many it kept", () => {
    expect(filterCount(3, 7)).toBe("3 of 7 transactions");
    expect(filterCount(1, 1)).toBe("1 of 1 transaction");
  });
});
