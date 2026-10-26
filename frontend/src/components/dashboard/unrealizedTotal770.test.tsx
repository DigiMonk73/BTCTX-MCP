// @vitest-environment jsdom
// Portfolio Overview's Unrealized Gains/Losses (#770): the bitcoin accounts'
// own gains added up, each its BTC's value at today's price to the cent less
// its cost, so the opened lines add up to it exactly. It was (price − the
// average cost rounded to the cent) × Total BTC, a few cents off them. The
// average cost shown stays as the server gives it.
import "../../test/setup";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { LivePrice } from "../../utils/dashboard";
import PortfolioOverview from "./PortfolioOverview";

const wallet = (account_id: number, name: string, value: string, cost_basis: number): AccountBalance => ({
  account_id, name, kind: "wallet", currency: "BTC", balance: value, exchange_id: null, exchange: null,
  hidden: false, cost_basis });

const BANK: AccountBalance = { account_id: 1, name: "Bank", kind: "bank", currency: "USD", balance: "100",
  exchange_id: null, exchange: null, hidden: false, cost_basis: null };

// $30,000.02 for 3 BTC: an average of $10,000.00666…, which the server rounds to $10,000.01
const TWO_WALLETS = [BANK, wallet(2, "Wallet", "1.00000000", 10000.01), wallet(100, "Coldcard", "2.00000000", 20000.01)];

const at = (value: number | null, loading = false): LivePrice => ({ loading, value, off: value === null && !loading });

const mount = (balances: AccountBalance[], price: LivePrice, averageCostBasis: number | null = 10000.01) =>
  render(<PortfolioOverview balances={balances} averageCostBasis={averageCostBasis} price={price} />);

const total = () => screen.getByText("Unrealized Gains/Losses").closest("p")!.textContent;

beforeEach(() => window.localStorage.clear());
afterEach(() => window.localStorage.clear());

describe("the card's Unrealized Gains/Losses", () => {
  it("is the accounts' own gains added up, not (price − rounded average) × Total BTC", async () => {
    mount(TWO_WALLETS, at(60000));
    // $49,999.99 + $99,999.99; the rounded average gave (60,000 − 10,000.01) × 3 = $149,999.97
    expect(total()).toBe("Unrealized Gains/Losses+$149,999.98");
    await userEvent.setup().click(screen.getByRole("button", { name: /^Wallet \(BTC\)/ }));
    const items = within(screen.getByRole("list", { name: "Wallet (BTC) accounts" })).getAllByRole("listitem");
    expect(items.map((item) => item.querySelector(".balance-line-cost span span")!.textContent)).toEqual([
      "+$49,999.99", "+$99,999.99"]);
  });

  it("keeps the average cost per BTC as the server gives it", () => {
    mount(TWO_WALLETS, at(60000));
    expect(screen.getByText("Avg. Cost per BTC").closest("p")!.textContent).toBe("Avg. Cost per BTC$10,000.01");
  });

  it("adds each account's value to the cent, so the parts add up at any price", () => {
    // Each worth $x.xx5 at this price: the sum of the cents, not the cents of the sum
    const halves = [BANK, wallet(2, "Wallet", "0.00000500", 0), wallet(100, "Coldcard", "0.00000500", 0),
      wallet(101, "Jade", "0.00000500", 0)];
    mount(halves, at(1001)); // 0.000005 BTC × $1,001 = $0.005005 each: $0.01 each
    expect(total()).toBe("Unrealized Gains/Losses+$0.03");
  });

  it("is a loss in red, and says why without a price, as before", () => {
    const { unmount } = mount(TWO_WALLETS, at(9000));
    expect(screen.getByText("−$3,000.02").className).toBe("text-loss");
    unmount();
    const off = mount(TWO_WALLETS, { loading: false, value: null, off: true });
    expect(total()).toBe("Unrealized Gains/LossesOffline");
    off.unmount();
    mount(TWO_WALLETS, at(null, true));
    expect(total()).toBe("Unrealized Gains/LossesLoading...");
  });
});
