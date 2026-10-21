// @vitest-environment jsdom
// B8-4 (spec 5.13): "An account filter on the page, in the browser like its
// other filters." One account's history: the rows naming it on either side.
import "../test/setup";
import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { byAccount } from "../utils/transactionList";
import { TWO_OF_EACH } from "../test/accountBooks";
import { renderTransactions, savedRow } from "../test/renderTransactions";

const tx = (id: number, from: number | null, to: number | null) =>
  ({ id, from_account_id: from, to_account_id: to }) as ITransaction;

describe("byAccount", () => {
  const rows = [tx(1, 99, 101), tx(2, 101, 103), tx(3, 103, 102), tx(4, 1, 4)];
  const ids = (list: ITransaction[]) => list.map((t) => t.id);

  it("keeps the rows naming the account on either side", () => {
    expect(ids(byAccount(rows, 103))).toEqual([2, 3]);
    expect(ids(byAccount(rows, 101))).toEqual([1, 2]);
  });

  it("keeps none for an account no row names", () => {
    expect(byAccount(rows, 5)).toEqual([]);
  });

  it("keeps every row, in the same order, for no account", () => {
    expect(ids(byAccount(rows, undefined))).toEqual([1, 2, 3, 4]);
  });
});

// Each row on its own day, so the list shows every one (newest first)
const ROWS = [
  savedRow(1, "Deposit", 99, 101, "0.5", { source: "MyBTC" }),
  savedRow(2, "Transfer", 101, 103, "0.1"),
  savedRow(3, "Sell", 103, 102, "0.05"),
  savedRow(4, "Buy", 1, 4, "0.2"),
  savedRow(5, "Deposit", 99, 104, "0.01", { source: "MyBTC" }),
];

const listed = () => screen.queryAllByRole("listitem").map((item) => item.querySelector(".tx-account")?.textContent);

describe("the page's account filter", () => {
  it("offers All accounts, then your accounts by nickname, hidden ones too; never the fee accounts", async () => {
    await renderTransactions({ book: TWO_OF_EACH, rows: ROWS });
    const filter = screen.getByRole("combobox", { name: "Filter by wallet, exchange or bank" });
    expect(within(filter).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "All accounts", "Bank", "Credit Union", "Wallet", "Cold Storage", "Old Wallet",
      "Exchange USD", "Exchange BTC", "Kraken USD", "Kraken BTC",
    ]);
    expect(filter).toHaveValue("");
    expect(listed()).toHaveLength(5);
  });

  it("shows one account's history, and every row again with All accounts", async () => {
    const { user } = await renderTransactions({ book: TWO_OF_EACH, rows: ROWS });
    const filter = screen.getByRole("combobox", { name: "Filter by wallet, exchange or bank" });
    await user.selectOptions(filter, "Kraken BTC");
    expect(listed()).toEqual([" · Kraken", " · Cold Storage → Kraken BTC"]);
    await user.selectOptions(filter, "Old Wallet");
    expect(listed()).toEqual([" · Old Wallet"]);
    await user.selectOptions(filter, "All accounts");
    expect(listed()).toHaveLength(5);
  });

  it("goes back to page 1 when the filter changes", async () => {
    const many = Array.from({ length: 12 }, (_, i) => savedRow(i + 1, "Deposit", 99, i < 11 ? 2 : 101, "0.01"));
    const { user } = await renderTransactions({ book: TWO_OF_EACH, rows: many });
    await user.click(screen.getByRole("button", { name: /next/i }));
    expect(listed()).toHaveLength(2);
    // Wallet's 11 rows: page 1 shows 10 (page 2 would show 1)
    await user.selectOptions(screen.getByRole("combobox", { name: "Filter by wallet, exchange or bank" }), "Wallet");
    expect(listed()).toHaveLength(10);
  });
});
