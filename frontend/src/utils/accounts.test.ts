// B6a-1: the book's answers in the frontend (spec 5.4), by id and kind, never by
// a fixed number or a nickname.
import { describe, expect, it } from "vitest";
import { MISSING, ONE_OF_EACH as ONE, RENAMED, TWO_OF_EACH as TWO } from "../test/accountBooks";
import { accountCurrency, accountKind, accountName, exchangeName, isBtcAccount, yours } from "./accounts";

describe("accountName", () => {
  it("is the nickname, External for 99, and says when the book lacks the id", () => {
    expect(accountName(TWO, 103)).toBe("Kraken BTC");
    expect(accountName(TWO, 99)).toBe("External");
    expect(accountName(TWO, MISSING)).toBe("account 999 (missing)");
  });
});

describe("exchangeName", () => {
  it("is an exchange account's exchange, else the account's own name", () => {
    expect(exchangeName(TWO, 103)).toBe("Kraken");
    expect(exchangeName(ONE, 4)).toBe("Exchange");
    expect(exchangeName(TWO, 101)).toBe("Cold Storage");
    expect(exchangeName(TWO, MISSING)).toBe("account 999 (missing)");
  });
});

describe("accountCurrency", () => {
  it("is the account's currency; none for External, a missing id or no id", () => {
    expect(accountCurrency(TWO, 102)).toBe("USD");
    expect(accountCurrency(TWO, 5)).toBe("BTC");
    expect(accountCurrency(TWO, 99)).toBeUndefined();
    expect(accountCurrency(TWO, MISSING)).toBeUndefined();
    expect(accountCurrency(TWO, undefined)).toBeUndefined();
  });
});

describe("accountKind", () => {
  it("is the account's kind; none for External", () => {
    expect(accountKind(TWO, 104)).toBe("wallet");
    expect(accountKind(TWO, 6)).toBe("fee");
    expect(accountKind(TWO, 99)).toBeUndefined();
  });
});

describe("isBtcAccount", () => {
  it.each([2, 4, 101, 103, 104])("account %s holds bitcoin (a hidden one too)", (id) => {
    expect(isBtcAccount(TWO, id)).toBe(true);
  });

  it.each([5, 1, 99, MISSING, undefined])("account %s doesn't (the fee account 5 is BTC, yet not one)", (id) => {
    expect(isBtcAccount(TWO, id)).toBe(false);
  });
});

describe("yours", () => {
  it("is the owner's accounts, hidden ones too, in the book's order; never a fee account", () => {
    expect(yours(TWO)).toEqual([1, 100, 2, 101, 104, 3, 4, 102, 103]);
    expect(yours(ONE)).toEqual([1, 2, 3, 4]);
  });
});

describe("a renamed book", () => {
  it("answers by id and kind, never by a 1.x name", () => {
    expect(accountName(RENAMED, 2)).toBe("Phone Wallet");
    expect(accountName(RENAMED, 4)).toBe("Coinbase BTC");
    expect(exchangeName(RENAMED, 4)).toBe("Coinbase");
    expect(isBtcAccount(RENAMED, 2)).toBe(true);
    expect(isBtcAccount(RENAMED, 4)).toBe(true);
    expect(yours(RENAMED)).toEqual([1, 2, 3, 4]);
  });
});
