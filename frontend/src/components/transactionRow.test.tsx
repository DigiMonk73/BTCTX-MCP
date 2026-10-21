// @vitest-environment jsdom
// B8-3 (spec 5.13): a Transactions row names its accounts from the book; a Buy
// or a Sell shows its exchange's name; any bitcoin account sent to itself is a
// "Consolidation"; dollars by the account's currency. Never a fixed id, never
// a 1.x name (RENAMED).
import "../test/setup";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import TransactionRow from "./TransactionRow";
import { parseTransaction } from "../utils/format";
import { MISSING, RENAMED, TWO_OF_EACH } from "../test/accountBooks";
import { renderTransactions, savedRow } from "../test/renderTransactions";
import { ACCOUNTS_FAILED } from "../utils/useAccounts";

function row(book: AccountBook, type: TransactionType, from: number | null, to: number | null, amount = "0.01") {
  const tx = parseTransaction(savedRow(1, type, from, to, amount));
  render(<TransactionRow tx={tx} book={book} onEdit={() => undefined} />);
  return screen.getByRole("listitem");
}

/** What the row's title says after the type: " · <accounts>". */
const accounts = (item: HTMLElement) => item.querySelector(".tx-account")?.textContent?.replace(/^ · /, "");
const subtitle = (item: HTMLElement) => item.querySelector(".tx-sub")?.textContent ?? "";
const amount = (item: HTMLElement) => item.querySelector(".tx-primary")?.textContent;

describe("a row's accounts, from the book (5.13)", () => {
  it("shows a Buy's and a Sell's exchange by its nickname", () => {
    expect(accounts(row(TWO_OF_EACH, "Buy", 100, 103))).toBe("Kraken");
  });

  it("shows a Sell on the first exchange as Exchange", () => {
    expect(accounts(row(TWO_OF_EACH, "Sell", 4, 3))).toBe("Exchange");
  });

  it("names both sides of a transfer", () => {
    expect(accounts(row(TWO_OF_EACH, "Transfer", 101, 4))).toBe("Cold Storage → Exchange BTC");
  });

  it("names a missing account", () => {
    expect(accounts(row(TWO_OF_EACH, "Deposit", 99, MISSING))).toBe(`account ${MISSING} (missing)`);
  });

  it("says N/A for no account", () => {
    expect(accounts(row(TWO_OF_EACH, "Withdrawal", null, 99))).toBe("N/A");
  });

  it("follows the owner's nicknames (RENAMED)", () => {
    expect(accounts(row(RENAMED, "Transfer", 2, 4))).toBe("Phone Wallet → Coinbase BTC");
  });

  it("shows RENAMED's Sell on its exchange's nickname", () => {
    expect(accounts(row(RENAMED, "Sell", 4, 3))).toBe("Coinbase");
  });
});

describe("Consolidation: any bitcoin account sent to itself (5.5)", () => {
  it.each([
    [2, TWO_OF_EACH], [103, TWO_OF_EACH], [4, TWO_OF_EACH], [2, RENAMED],
  ])("a transfer from %i to itself", (id, book) => {
    const item = row(book, "Transfer", id, id);
    expect(subtitle(item)).toContain("Consolidation");
    expect(subtitle(item)).not.toContain("Between exchanges");
  });

  it("isn't said of a transfer between two missing ids", () => {
    expect(subtitle(row(TWO_OF_EACH, "Transfer", MISSING, MISSING))).not.toContain("Consolidation");
  });
});

describe("dollars by the account's currency", () => {
  it("shows a deposit into an added bank in dollars", () => {
    expect(amount(row(TWO_OF_EACH, "Deposit", 99, 100, "500"))).toBe("+$500.00");
  });

  it("shows a deposit into an added wallet in bitcoin", () => {
    expect(amount(row(TWO_OF_EACH, "Deposit", 99, 101, "0.01"))).toBe("+0.01000000 BTC");
  });

  it("shows a withdrawal from RENAMED's Checking in dollars", () => {
    expect(amount(row(RENAMED, "Withdrawal", 1, 99, "20"))).toBe("−$20.00");
  });
});

describe("the page passes the book (5.13)", () => {
  it("names a Buy on the second exchange on the page", async () => {
    await renderTransactions({ book: TWO_OF_EACH, rows: [savedRow(1, "Buy", 100, 103, "0.1")] });
    expect(accounts(screen.getByRole("listitem"))).toBe("Kraken");
  });

  it("says the book couldn't load, in place of the list", async () => {
    await renderTransactions({ book: TWO_OF_EACH, rows: [savedRow(1, "Buy", 100, 103, "0.1")], accountsFail: true });
    expect(screen.getByRole("alert")).toHaveTextContent(ACCOUNTS_FAILED);
    expect(screen.queryByRole("listitem")).toBeNull();
  });
});
