// @vitest-environment jsdom
// B7b-1's proving test: Settings' "Wallets, exchanges and banks" lists each of
// your accounts with its nickname, kind and balance, hidden ones marked, the fee
// accounts never (spec 5.9).
import { describe, expect, it } from "vitest";
import { screen, within } from "@testing-library/react";
import { ONE_OF_EACH, RENAMED, TWO_BALANCES, TWO_OF_EACH } from "../../test/accountBooks";
import { renderSettings } from "../../test/renderSettings";
import { balanceText, KIND_LABEL, settingsAccounts } from "../../utils/ledgerAccounts";

const byId = (book: AccountBook, id: number) => book.find((a) => a.id === id) as LedgerAccount;

/** The section's rows, by their accessible names, in order. */
function rowNames(): string[] {
  const list = screen.getByRole("list", { name: "Your accounts" });
  return within(list).getAllByRole("listitem").map((row) => row.getAttribute("aria-label") ?? "");
}

describe("the book's answers for the list (utils/ledgerAccounts.ts)", () => {
  it("names each kind", () => {
    expect(KIND_LABEL).toEqual({ bank: "Bank", wallet: "Wallet", exchange: "Exchange", fee: "Fee" });
  });

  it("lists your accounts in the book's order, hidden ones too, never the fee accounts", () => {
    expect(settingsAccounts(TWO_OF_EACH).map((a) => a.id)).toEqual([1, 100, 2, 101, 104, 3, 4, 102, 103]);
    expect(settingsAccounts(ONE_OF_EACH).map((a) => a.id)).toEqual([1, 2, 3, 4]);
  });

  it("writes a balance in its account's currency", () => {
    expect(balanceText(TWO_BALANCES, byId(TWO_OF_EACH, 100))).toBe("$250.00");
    expect(balanceText(TWO_BALANCES, byId(TWO_OF_EACH, 3))).toBe("$1,200.50");
    expect(balanceText(TWO_BALANCES, byId(TWO_OF_EACH, 101))).toBe("0.25000000 BTC");
    expect(balanceText(TWO_BALANCES, byId(TWO_OF_EACH, 104))).toBe("0.00000000 BTC");
  });

  it("finds a balance by the account's id, never its name", () => {
    const renamedBalance = [{ account_id: 1, name: "Bank", currency: "USD", balance: "12.00" }];
    expect(balanceText(renamedBalance, byId(RENAMED, 1))).toBe("$12.00");
  });

  it("is blank for an account the balances don't list", () => {
    expect(balanceText([], byId(TWO_OF_EACH, 100))).toBe("");
  });
});

describe("the section (components/LedgerAccounts.tsx)", () => {
  it("is a region titled as the spec names it", async () => {
    await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    const region = screen.getByRole("region", { name: "Wallets, exchanges and banks" });
    expect(within(region).getByRole("heading", { name: "Wallets, exchanges and banks" })).toBeInTheDocument();
  });

  it("lists your accounts in 5.9's order, by nickname, never the fee accounts", async () => {
    await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    expect(rowNames()).toEqual([
      "Bank", "Credit Union", "Wallet", "Cold Storage", "Old Wallet",
      "Exchange USD", "Exchange BTC", "Kraken USD", "Kraken BTC",
    ]);
    expect(screen.queryByText("BTC Fees")).toBeNull();
    expect(screen.queryByText("USD Fees")).toBeNull();
  });

  it("shows each row's kind and balance", async () => {
    await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    expect(screen.getByRole("listitem", { name: "Credit Union" })).toHaveTextContent("Credit Union");
    expect(screen.getByRole("listitem", { name: "Credit Union" })).toHaveTextContent("Bank · $250.00");
    expect(screen.getByRole("listitem", { name: "Cold Storage" })).toHaveTextContent("Wallet · 0.25000000 BTC");
    expect(screen.getByRole("listitem", { name: "Kraken BTC" })).toHaveTextContent("Exchange · 0.05000000 BTC");
  });

  it("shows only the kind when the balances don't list the account", async () => {
    await renderSettings({ book: TWO_OF_EACH, balances: [] });
    const row = screen.getByRole("listitem", { name: "Credit Union" });
    expect(row).toHaveTextContent("Bank");
    expect(row).not.toHaveTextContent("·");
  });

  it("marks a hidden account, and only it", async () => {
    await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    expect(screen.getByRole("listitem", { name: "Old Wallet" })).toHaveTextContent("Hidden");
    expect(screen.getAllByText("Hidden")).toHaveLength(1);
  });

  it("shows the owner's nicknames (RENAMED)", async () => {
    await renderSettings({ book: RENAMED });
    expect(rowNames()).toEqual(["Checking", "Phone Wallet", "Coinbase USD", "Coinbase BTC"]);
  });

  it("asks the book and the balances once each", async () => {
    const { requests } = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    expect(requests.map((r) => `${r.method} ${r.url}`).sort()).toEqual([
      "get /accounts/", "get /calculations/accounts/balances",
    ]);
  });

  it("says so when the book won't load (D4), and lists nothing", async () => {
    await renderSettings({ book: TWO_OF_EACH, accountsFail: true });
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load your accounts: reload the page.");
    expect(screen.queryByRole("list", { name: "Your accounts" })).toBeNull();
  });
});
