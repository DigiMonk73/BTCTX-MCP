// The account book's answers by id, and what each of the form's pickers
// offers (2.0 spec 5.4, 5.5, 5.13).
import { describe, expect, it } from "vitest";
import { MANY, MISSING_ID, ONE_OF_EACH } from "../test/books";
import {
  EXTERNAL_ID,
  accountCurrency,
  accountKind,
  accountName,
  btcOf,
  buyExchanges,
  buyPayers,
  byKind,
  chosenId,
  exchangeCount,
  exchangeName,
  isBtcAccount,
  sellExchanges,
  transferTargets,
  usdOf,
  visibleAccounts,
  yours,
} from "./accounts";

describe("the book's answers by id", () => {
  it("names an account by its name, External by its own, and a missing one as missing", () => {
    expect(accountName(MANY, 100)).toBe("Coldcard");
    expect(accountName(MANY, 5)).toBe("BTC Fees");
    expect(accountName(MANY, EXTERNAL_ID)).toBe("External");
    expect(accountName(MANY, MISSING_ID)).toBe(`account ${MISSING_ID} (missing)`);
  });

  it("names an exchange's account by its exchange, any other by its own name", () => {
    expect(exchangeName(MANY, 103)).toBe("Kraken");
    expect(exchangeName(MANY, 102)).toBe("Kraken");
    expect(exchangeName(ONE_OF_EACH, 4)).toBe("Exchange");
    expect(exchangeName(MANY, 2)).toBe("Sparrow");
    expect(exchangeName(MANY, MISSING_ID)).toBe(`account ${MISSING_ID} (missing)`);
  });

  it("says an account's currency and kind; none for External or a missing id", () => {
    expect([accountCurrency(MANY, 101), accountKind(MANY, 101)]).toEqual(["USD", "bank"]);
    expect([accountCurrency(MANY, 103), accountKind(MANY, 103)]).toEqual(["BTC", "exchange"]);
    expect([accountCurrency(MANY, EXTERNAL_ID), accountKind(MANY, EXTERNAL_ID)]).toEqual([undefined, undefined]);
    expect([accountCurrency(MANY, MISSING_ID), accountKind(MANY, undefined)]).toEqual([undefined, undefined]);
  });

  it("calls a wallet or an exchange's BTC account bitcoin, never a fee account or a missing id", () => {
    expect([2, 100, 104, 4, 103].map((id) => isBtcAccount(MANY, id))).toEqual([true, true, true, true, true]);
    expect([1, 101, 3, 102, 5, 6, EXTERNAL_ID, MISSING_ID, undefined].some((id) => isBtcAccount(MANY, id))).toBe(false);
  });

  it("pairs an exchange's two accounts", () => {
    expect([usdOf(MANY, 103), btcOf(MANY, 102), usdOf(MANY, 102), btcOf(MANY, 103)]).toEqual([102, 103, 102, 103]);
    expect([usdOf(ONE_OF_EACH, 4), btcOf(ONE_OF_EACH, 3)]).toEqual([3, 4]);
    expect([usdOf(MANY, 2), btcOf(MANY, 1), usdOf(MANY, MISSING_ID), btcOf(MANY, undefined)])
      .toEqual([undefined, undefined, undefined, undefined]);
  });

  it("counts the exchanges, hidden ones too, each as one", () => {
    expect([exchangeCount(ONE_OF_EACH), exchangeCount(MANY)]).toEqual([1, 3]);
  });

  it("lists the owner's accounts, hidden ones too, never a fee account", () => {
    expect(yours(MANY)).toEqual([1, 101, 2, 100, 104, 3, 4, 102, 103, 105, 106]);
    expect(yours(ONE_OF_EACH)).toEqual([1, 2, 3, 4]);
  });

  it("reads a picker's value as an id: blank is none", () => {
    expect([chosenId(""), chosenId(undefined), chosenId(null), chosenId("103"), chosenId(4)])
      .toEqual([undefined, undefined, undefined, 103, 4]);
    expect(chosenId("abc")).toBeUndefined();
  });
});

describe("what a picker offers", () => {
  it("leaves hidden accounts out, but the row's own", () => {
    expect(visibleAccounts(MANY)).toEqual([1, 101, 2, 100, 3, 4, 102, 103]);
    expect(visibleAccounts(MANY, 104)).toEqual([1, 101, 2, 100, 104, 3, 4, 102, 103]);
    expect(visibleAccounts(MANY, 5)).toEqual(visibleAccounts(MANY)); // a fee account is never one
    expect(visibleAccounts(ONE_OF_EACH)).toEqual([1, 2, 3, 4]);
  });

  it("sends a Transfer within its currency, to itself last and only from a bitcoin account", () => {
    expect(transferTargets(MANY, 2)).toEqual([100, 4, 103, 2]);
    expect(transferTargets(MANY, 4)).toEqual([2, 100, 103, 4]);
    expect(transferTargets(MANY, 1)).toEqual([101, 3, 102]);
    expect(transferTargets(MANY, 102)).toEqual([1, 101, 3]);
    expect(transferTargets(MANY, 2, 104)).toEqual([100, 104, 4, 103, 2]);
    expect(transferTargets(MANY, 1, 104)).toEqual([101, 3, 102]); // a kept account of another currency isn't offered
    expect(transferTargets(ONE_OF_EACH, 1)).toEqual([3]);
    expect(transferTargets(ONE_OF_EACH, 3)).toEqual([1]);
    expect(transferTargets(ONE_OF_EACH, 2)).toEqual([4, 2]);
    expect(transferTargets(ONE_OF_EACH, 4)).toEqual([2, 4]);
  });

  it("sends a Transfer from External, a fee account or a missing id nowhere", () => {
    expect([EXTERNAL_ID, 5, MISSING_ID, undefined].map((id) => transferTargets(MANY, id))).toEqual([[], [], [], []]);
  });

  it("buys on any exchange's BTC account", () => {
    expect(buyExchanges(MANY)).toEqual([4, 103]);
    expect(buyExchanges(MANY, 106)).toEqual([4, 103, 106]);
    expect(buyExchanges(ONE_OF_EACH)).toEqual([4]);
  });

  it("pays for a Buy from that exchange's dollars or a bank, nothing before its exchange (Q15)", () => {
    expect(buyPayers(MANY, 103)).toEqual([102, 1, 101]);
    expect(buyPayers(MANY, 4)).toEqual([3, 1, 101]);
    expect(buyPayers(ONE_OF_EACH, 4)).toEqual([3, 1]);
    expect(buyPayers(MANY, undefined)).toEqual([]);
    expect(buyPayers(MANY, 2)).toEqual([]); // a wallet isn't an exchange
    expect(buyPayers(MANY, 106)).toEqual([1, 101]); // a hidden exchange's dollars, only for its own row
    expect(buyPayers(MANY, 106, 105)).toEqual([105, 1, 101]);
  });

  it("sells from any exchange's BTC account", () => {
    expect(sellExchanges(MANY)).toEqual([4, 103]);
    expect(sellExchanges(MANY, 106)).toEqual([4, 103, 106]);
    expect(sellExchanges(ONE_OF_EACH)).toEqual([4]);
  });
});

describe("a picker's groups (P7's mockups)", () => {
  it("groups by kind once there is more than one of a kind", () => {
    expect(byKind(MANY, [1, 101, 2, 100, 3, 4, 102, 103])).toEqual([
      { label: "Banks", ids: [1, 101] },
      { label: "Wallets", ids: [2, 100] },
      { label: "Exchanges", ids: [3, 4, 102, 103] },
    ]);
    expect(byKind(MANY, [102, 1, 101])).toEqual([
      { label: "Exchanges", ids: [102] },
      { label: "Banks", ids: [1, 101] },
    ]);
  });

  it("doesn't group one of each: an exchange's two accounts are one exchange", () => {
    expect(byKind(ONE_OF_EACH, [1, 2, 3, 4])).toBeNull();
    expect(byKind(MANY, [100, 4, 103, 2])).toEqual([
      { label: "Wallets", ids: [100, 2] },
      { label: "Exchanges", ids: [4, 103] },
    ]);
    expect(byKind(MANY, [3, 1])).toBeNull();
    expect(byKind(MANY, [4, 103])).toBeNull(); // one kind: nothing to tell apart
    expect(byKind(MANY, [1, 101])).toBeNull();
  });
});
