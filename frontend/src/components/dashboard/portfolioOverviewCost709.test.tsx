// @vitest-environment jsdom
// Each account's own cost on Portfolio Overview (#709, the owner's decision
// of 2026-10-25): an opened Wallet (BTC) or Exchange (BTC) line shows each
// account's cost basis, the server's figure as it gave it, and, with a
// price, its unrealized gain beside its amount. Total BTC and the average
// cost stay as they are, the card's gain is the accounts' added up (#770),
// and with one account of each kind there's no list.
import "../../test/setup";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { LivePrice } from "../../utils/dashboard";
import PortfolioOverview from "./PortfolioOverview";

const balance = (
  account_id: number, name: string, kind: AccountBalance["kind"], currency: string, value: string,
  cost_basis: number | null, extra: Partial<Pick<AccountBalance, "exchange_id" | "exchange" | "hidden">> = {},
): AccountBalance => ({ account_id, name, kind, currency, balance: value, exchange_id: null, exchange: null,
  hidden: false, cost_basis, ...extra });

const EXCHANGE = { exchange_id: 1, exchange: "Exchange" };
const KRAKEN = { exchange_id: 2, exchange: "Kraken" };

const ONE_OF_EACH = [
  balance(1, "Bank", "bank", "USD", "1500.25", null),
  balance(2, "Wallet", "wallet", "BTC", "0.50000000", 9000.01),
  balance(3, "Exchange USD", "exchange", "USD", "20.00", null, EXCHANGE),
  balance(4, "Exchange BTC", "exchange", "BTC", "0.25000000", 6000, EXCHANGE),
  balance(5, "BTC Fees", "fee", "BTC", "0.00010000", null),
  balance(6, "USD Fees", "fee", "USD", "12.00", null),
];

/** Multiple wallets (a hidden one still holding coins, at a loss; an empty one) and two exchanges. */
const MULTIPLE = [
  ...ONE_OF_EACH,
  balance(100, "Coldcard", "wallet", "BTC", "0.25000000", 5000.5),
  balance(103, "Paper Wallet", "wallet", "BTC", "0.01000000", 900, { hidden: true }),
  balance(104, "Jade", "wallet", "BTC", "0.00000000", 0),
  balance(101, "Kraken USD", "exchange", "USD", "0.00", null, KRAKEN),
  balance(102, "Kraken BTC", "exchange", "BTC", "0.05000000", 1234.56, KRAKEN),
];

const PRICE: LivePrice = { loading: false, value: 60000, off: false };

const mount = (balances: AccountBalance[], price: LivePrice = PRICE) =>
  render(<PortfolioOverview balances={balances} averageCostBasis={20000} price={price} />);

const lineButton = (label: string) => screen.getByRole("button", { name: new RegExp(`^${label.replace(/[()]/g, "\\$&")}`) });

async function opened(label: string): Promise<HTMLElement[]> {
  await userEvent.setup().click(lineButton(label));
  return within(screen.getByRole("list", { name: `${label} accounts` })).getAllByRole("listitem");
}

const words = (item: HTMLElement) => item.querySelector(".balance-line-cost")?.textContent ?? null;

beforeEach(() => window.localStorage.clear());
afterEach(() => window.localStorage.clear());

describe("each account's cost when a bitcoin line is opened", () => {
  it("Wallet (BTC): each wallet's cost basis as the server gave it, and its gain at today's price", async () => {
    mount(MULTIPLE);
    const items = await opened("Wallet (BTC)");
    expect(items.map(words)).toEqual([
      "Cost basis $9,000.01Unrealized +$20,999.99", // 0.5 BTC at $60,000 is $30,000.00
      "Cost basis $5,000.50Unrealized +$9,999.50",
      "Cost basis $900.00Unrealized −$300.00",
      null, // the empty Jade: nothing to cost
    ]);
    // Beside its amount, name and amount as before
    expect(items[1].textContent).toBe("Coldcard0.25000000 BTCCost basis $5,000.50Unrealized +$9,999.50");
  });

  it("colours a gain green and a loss red", async () => {
    mount(MULTIPLE);
    const items = await opened("Wallet (BTC)");
    expect(within(items[0]).getByText("+$20,999.99").className).toBe("text-gain");
    expect(within(items[2]).getByText("−$300.00").className).toBe("text-loss");
  });

  it("Exchange (BTC): each exchange's bitcoin with its cost; Exchange (USD)'s dollars have none", async () => {
    mount(MULTIPLE);
    expect((await opened("Exchange (BTC)")).map(words)).toEqual([
      "Cost basis $6,000.00Unrealized +$9,000.00", "Cost basis $1,234.56Unrealized +$1,765.44"]);
    expect((await opened("Exchange (USD)")).map(words)).toEqual([null, null]);
  });

  it("without a price, the cost only: nothing is guessed", async () => {
    for (const price of [{ loading: false, value: null, off: true }, { loading: true, value: null, off: false }]) {
      window.localStorage.clear();
      const { unmount } = mount(MULTIPLE, price);
      expect((await opened("Wallet (BTC)")).map(words)).toEqual([
        "Cost basis $9,000.01", "Cost basis $5,000.50", "Cost basis $900.00", null]);
      unmount();
    }
  });

  it("the totals: Total BTC, the average cost as the server gives it, and the accounts' gains added up (#770)", async () => {
    const { container } = mount(MULTIPLE);
    await opened("Wallet (BTC)");
    const totals = [...container.querySelectorAll(".portfolio-overview > hr ~ p")].map((p) => p.textContent);
    expect(totals).toEqual([
      "Total BTC1.06000000 BTC", "Avg. Cost per BTC$20,000.00", "Unrealized Gains/Losses+$41,464.93"]);
  });
});

describe("with one account of each kind", () => {
  it("has 1.2.10's lines still: no list, no cost lines", () => {
    const { container } = mount(ONE_OF_EACH);
    expect([...container.querySelectorAll(".portfolio-overview p")].map((p) => p.textContent)).toEqual([
      "Bank (USD)$1,500.25", "Exchange (USD)$20.00", "Exchange (BTC)0.25000000 BTC", "Wallet (BTC)0.50000000 BTC",
      "Total BTC0.75000000 BTC", "Avg. Cost per BTC$20,000.00", "Unrealized Gains/Losses+$29,999.99",
    ]); // the gain is the two accounts' own ($20,999.99 + $9,000.00, #770)
    expect(container.querySelectorAll(".balance-line-cost")).toHaveLength(0);
  });
});
