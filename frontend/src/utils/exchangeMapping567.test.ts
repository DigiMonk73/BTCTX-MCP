// B5b (#567): matching another exchange's columns, the owner's own mapping.
import { describe, expect, it } from "vitest";
import {
  draftFrom, emptyDraft, guessColumns, guessKinds, mappingFrom, missingRoles, ROLES, type Draft,
} from "./exchangeMapping";

const COLUMNS = ["When", "Type", "Coins", "Dollars", "Charge", "Charge In", "Ref", "State"];

describe("guessColumns", () => {
  it("guesses a column by its usual names, never two roles from one column", () => {
    const found = guessColumns(["Timestamp", "Transaction Type", "Amount BTC", "Amount USD", "Fee USD", "Status", "ID"]);
    expect(found).toMatchObject({
      date: "Timestamp", kind: "Transaction Type", btc: "Amount BTC", usd: "Amount USD", fee: "Fee USD",
      status: "Status", row_id: "ID",
    });
  });

  it("leaves a role blank when no column is named for it", () => {
    expect(guessColumns(COLUMNS)).toEqual({ kind: "Type", status: "State", row_id: "Ref" });
    expect(guessColumns(["When", "Coins", "Dollars", "Charge"])).toEqual({});
  });
});

describe("guessKinds", () => {
  it("takes only the words that can mean one thing; the rest are the owner's to choose", () => {
    expect(guessKinds(["Bought", "Buy", "Purchase", "Sold", "Sale", "Sell", "Deposit", "Withdrawal", "Card"])).toEqual({
      Bought: "buy", Buy: "buy", Purchase: "buy", Sold: "sell", Sale: "sell", Sell: "sell",
    });
  });
});

describe("mappingFrom", () => {
  const draft: Draft = {
    ...emptyDraft(),
    name: "  Example Exchange ",
    columns: { date: "When", kind: "Type", btc: "Coins", usd: "Dollars", fee: "Charge", fee_currency: "Charge In",
      status: "State", row_id: "" },
    kinds: { Bought: "buy", Sold: "sell", Withdrew: "send", Card: "" },
    zone: "America/Chicago",
    buyAfterFee: true,
    done: ["done"],
  };

  it("sends only the columns chosen and the words given a kind", () => {
    expect(mappingFrom(draft)).toEqual({
      name: "Example Exchange",
      columns: { date: "When", kind: "Type", btc: "Coins", usd: "Dollars", fee: "Charge", fee_currency: "Charge In",
        status: "State" },
      kinds: { Bought: "buy", Sold: "sell", Withdrew: "send" },
      zone: "America/Chicago",
      dollars_after_fee: ["buy"],
      send_fee_included: false,
      decimal_comma: false,
      day_first: false,
      btc_assets: ["BTC"],
      done: ["done"],
    });
  });

  it("is the draft it was made from, read back", () => {
    expect(mappingFrom(draftFrom(mappingFrom(draft)))).toEqual(mappingFrom(draft));
  });
});

describe("missingRoles", () => {
  it("names the columns a mapping needs before it can read a file", () => {
    expect(missingRoles(emptyDraft()).map((r) => r.label)).toEqual(["Date", "Kind of row", "Bitcoin amount"]);
    const draft = { ...emptyDraft(), columns: { date: "When", kind: "Type", btc: "Coins" }, kinds: { Bought: "buy" } };
    expect(missingRoles(draft)).toEqual([]);
  });

  it("asks for at least one word read as a kind", () => {
    const draft = { ...emptyDraft(), columns: { date: "When", kind: "Type", btc: "Coins" } };
    expect(missingRoles(draft).map((r) => r.label)).toEqual(["What each kind of row is"]);
  });

  it("lists every role with a label the matcher shows", () => {
    expect(ROLES.map((r) => r.role)).toEqual(
      ["date", "time", "kind", "btc", "usd", "fee", "fee_currency", "fee_btc", "asset", "status", "row_id"]);
    expect(ROLES.every((r) => r.label && r.hint)).toBe(true);
  });
});
