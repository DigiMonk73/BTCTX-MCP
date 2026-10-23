// @vitest-environment jsdom
// The form's account pickers on a new transaction (2.0 spec 5.13, #351): ids
// from the book, blank and required unless exactly one fits, hidden
// accounts and the fee accounts left out, grouped by kind once there's
// more than one of a kind (P7), and with one of each the form 1.x showed,
// but for a new Buy's "Paid from", which starts blank.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MANY, ONE_OF_EACH } from "../../test/books";
import { offered, renderForm, shown } from "../../test/renderForm";
import { ACCOUNTS_FAILED } from "../../utils/useAccounts";

const WITHIN_WALLET = "Wallet: consolidate / move within the same wallet";
const WITHIN_EXCHANGE = "Exchange: move between exchanges BitcoinTX counts as one";

describe("with one of each, the form 1.x showed", () => {
  it("a Deposit or Withdrawal's account, its currency the account's", async () => {
    const form = await renderForm({ book: ONE_OF_EACH });
    await form.pickType("Deposit");
    expect(offered("Account")).toEqual(["Bank", "Wallet", "Exchange USD", "Exchange BTC"]);
    expect([shown("Account"), shown("Currency")]).toEqual(["Select Account", ""]);
    await form.choose("Account", "Exchange BTC");
    expect(shown("Currency")).toBe("BTC");
    expect(screen.getByLabelText("Source")).toBeTruthy();
    await form.choose("Account", "Exchange USD");
    expect(shown("Currency")).toBe("USD");
    expect(screen.queryByLabelText("Source")).toBeNull();
  });

  it("a Transfer: To filled when one fits, else blank", async () => {
    const form = await renderForm({ book: ONE_OF_EACH });
    await form.pickType("Transfer");
    expect(offered("From Account")).toEqual(["Bank", "Wallet", "Exchange USD", "Exchange BTC"]);
    await form.choose("From Account", "Bank");
    expect([shown("From Currency"), shown("To Account"), shown("To Currency")]).toEqual(["USD", "Exchange USD", "USD"]);
    await form.choose("From Account", "Exchange USD");
    expect(shown("To Account")).toBe("Bank");
    await form.choose("From Account", "Wallet");
    expect(offered("To Account")).toEqual(["Exchange BTC", WITHIN_WALLET]);
    expect(shown("To Account")).toBe("Select To Account");
    await form.choose("From Account", "Exchange BTC");
    expect(offered("To Account")).toEqual(["Wallet", WITHIN_EXCHANGE]);
  });

  it("a Buy: no exchange to choose, and Paid from starts blank", async () => {
    const form = await renderForm({ book: ONE_OF_EACH });
    await form.pickType("Buy");
    expect(screen.queryByLabelText("Exchange", { exact: true })).toBeNull();
    expect(offered("Paid from")).toEqual(["Exchange USD", "Bank (auto-buy)"]);
    expect(shown("Paid from")).toBe("Select Account");
  });

  it("a Sell: its exchange, read-only", async () => {
    const form = await renderForm({ book: ONE_OF_EACH });
    await form.pickType("Sell");
    const account = screen.getByLabelText("Account", { exact: true }) as HTMLInputElement;
    expect([account.tagName, account.value, account.readOnly]).toEqual(["INPUT", "Exchange", true]);
  });
});

describe("with more accounts", () => {
  it("lists the visible ones by kind, never a fee account", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Deposit");
    expect(offered("Account")).toEqual([
      "Banks: Checking", "Banks: Savings", "Wallets: Sparrow", "Wallets: Coldcard",
      "Exchanges: River USD", "Exchanges: River BTC", "Exchanges: Kraken USD", "Exchanges: Kraken BTC",
    ]);
  });

  it("sends a Transfer only within its currency, itself only as a bitcoin account's consolidation", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Transfer");
    await form.choose("From Account", "Coldcard");
    expect(offered("To Account")).toEqual([
      "Wallets: Sparrow", "Wallets: Coldcard: consolidate / move within the same wallet",
      "Exchanges: River BTC", "Exchanges: Kraken BTC",
    ]);
    expect(shown("To Account")).toBe("Select To Account");
    await form.choose("From Account", "Kraken USD");
    expect(offered("To Account")).toEqual(["Banks: Checking", "Banks: Savings", "Exchanges: River USD"]);
  });

  it("forgets a To that the new From doesn't allow", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Transfer");
    await form.choose("From Account", "Coldcard");
    await form.choose("To Account", "Kraken BTC");
    await form.choose("From Account", "Checking");
    expect(shown("To Account")).toBe("Select To Account");
    await form.choose("From Account", "Sparrow");
    expect(shown("To Account")).toBe("Select To Account");
  });

  it("buys on a chosen exchange, paid from its dollars or a bank (Q15)", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Buy");
    expect(offered("Exchange")).toEqual(["River", "Kraken"]);
    expect(shown("Exchange")).toBe("Select Exchange");
    expect(offered("Paid from")).toEqual([]);
    await form.choose("Exchange", "Kraken");
    expect(offered("Paid from")).toEqual([
      "Exchanges: Kraken USD", "Banks: Checking (auto-buy)", "Banks: Savings (auto-buy)",
    ]);
    await form.choose("Paid from", "Kraken USD");
    await form.choose("Exchange", "River");
    expect(shown("Paid from")).toBe("Select Account"); // Kraken's dollars don't buy on River
  });

  it("sells on a chosen exchange", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Sell");
    expect(offered("Account")).toEqual(["River", "Kraken"]);
    expect(shown("Account")).toBe("Select Exchange");
  });

  it("saves the ids chosen", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Buy");
    await form.choose("Exchange", "Kraken");
    await form.choose("Paid from", "Savings (auto-buy)");
    await form.user.type(screen.getByLabelText("Amount USD"), "1000");
    await form.user.type(screen.getByLabelText("Amount BTC"), "0.01");
    await form.save();
    expect(form.sent()).toMatchObject({ type: "Buy", from_account_id: 101, to_account_id: 103, amount: 0.01 });
  });

  it("refuses to save until an account is chosen", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Sell");
    await form.user.type(screen.getByLabelText("Amount BTC"), "0.01");
    await form.user.type(screen.getByLabelText("Gross Proceeds (USD)"), "600");
    await form.save();
    expect(screen.getByText("Please select an exchange")).toBeTruthy();
    expect(form.sent()).toBeUndefined();
  });
});

it("says so when the accounts won't load, and offers no account to save into", async () => {
  const form = await renderForm({ book: ONE_OF_EACH, accountsFail: true });
  await form.pickType("Deposit");
  expect(screen.getByText(ACCOUNTS_FAILED)).toBeTruthy();
  expect(screen.queryByLabelText("Account", { exact: true })).toBeNull();
});
