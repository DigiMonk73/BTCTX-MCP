// @vitest-environment jsdom
// Portfolio Overview as 1.2.10's card, with a caret per kind (#674): each
// kind's line its total; a caret, the whole line a button, where a kind has
// more than one account or a hidden one still holding something, listing
// them under it; closed by default, remembered on this device.
import "../../test/setup";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OPEN_LINES_KEY, type LivePrice } from "../../utils/dashboard";
import PortfolioOverview from "./PortfolioOverview";

const balance = (
  account_id: number, name: string, kind: AccountBalance["kind"], currency: string, value: string,
  extra: Partial<Pick<AccountBalance, "exchange_id" | "exchange" | "hidden">> = {},
): AccountBalance => ({ account_id, name, kind, currency, balance: value, exchange_id: null, exchange: null,
  hidden: false, ...extra });

const EXCHANGE = { exchange_id: 1, exchange: "Exchange" };
const KRAKEN = { exchange_id: 2, exchange: "Kraken" };

const ONE_OF_EACH = [
  balance(1, "Bank", "bank", "USD", "1500.25"),
  balance(2, "Wallet", "wallet", "BTC", "0.50000000"),
  balance(3, "Exchange USD", "exchange", "USD", "20.00", EXCHANGE),
  balance(4, "Exchange BTC", "exchange", "BTC", "0.25000000", EXCHANGE),
  balance(5, "BTC Fees", "fee", "BTC", "0.00010000"),
  balance(6, "USD Fees", "fee", "USD", "12.00"),
];

/** Two wallets (and a hidden one still holding coins) and two exchanges; one bank. */
const TWO_WALLETS_TWO_EXCHANGES = [
  ...ONE_OF_EACH,
  balance(100, "Coldcard", "wallet", "BTC", "0.25000000"),
  balance(103, "Paper Wallet", "wallet", "BTC", "0.01000000", { hidden: true }),
  balance(101, "Kraken USD", "exchange", "USD", "0.00", KRAKEN),
  balance(102, "Kraken BTC", "exchange", "BTC", "0.05000000", KRAKEN),
];

const PRICE: LivePrice = { loading: false, value: 60000, off: false };

const mount = (balances: AccountBalance[]) =>
  render(<PortfolioOverview balances={balances} averageCostBasis={20000} price={PRICE} />);

const expanded = (button: HTMLElement) => button.getAttribute("aria-expanded") === "true";

const lineButton = (label: string) => screen.getByRole("button", { name: new RegExp(`^${label.replace(/[()]/g, "\\$&")}`) });

beforeEach(() => window.localStorage.clear());
afterEach(() => window.localStorage.clear());

describe("Portfolio Overview with one account of each kind", () => {
  it("is 1.2.10's card: the four kinds, a divider, then Total BTC, average cost and unrealized gains; no caret", () => {
    const { container } = mount(ONE_OF_EACH);
    const card = container.querySelector(".portfolio-overview")!;
    expect([...card.querySelectorAll("p")].map((p) => p.textContent)).toEqual([
      "Bank (USD)$1,500.25", "Exchange (USD)$20.00", "Exchange (BTC)0.25000000 BTC", "Wallet (BTC)0.50000000 BTC",
      "Total BTC0.75000000 BTC", "Avg. Cost per BTC$20,000.00", "Unrealized Gains/Losses+$30,000.00",
    ]);
    expect(card.querySelectorAll("p:nth-of-type(4) + hr")).toHaveLength(1);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
    expect(screen.queryAllByRole("list")).toHaveLength(0);
  });
});

describe("Portfolio Overview with two wallets and two exchanges", () => {
  it("each kind's line shows its total; a caret on the kinds with more than one, closed", () => {
    mount(TWO_WALLETS_TWO_EXCHANGES);
    expect(screen.getByText("Bank (USD)").closest("p")!.textContent).toBe("Bank (USD)$1,500.25");
    expect(screen.queryByRole("button", { name: /^Bank/ })).toBeNull();
    for (const [label, total] of [["Exchange (USD)", "$20.00"], ["Exchange (BTC)", "0.30000000 BTC"],
      ["Wallet (BTC)", "0.76000000 BTC"]]) {
      const button = lineButton(label);
      expect(button.textContent).toBe(`${label}${total}`);
      expect(expanded(button)).toBe(false);
      const list = document.getElementById(button.getAttribute("aria-controls")!)!;
      expect(list).not.toBeNull();
      expect(list.hidden).toBe(true);
    }
  });

  it("the caret opens a kind's list under its line, each account's name and amount, Hidden noted, and closes it", async () => {
    const user = userEvent.setup();
    mount(TWO_WALLETS_TWO_EXCHANGES);
    const wallet = lineButton("Wallet (BTC)");
    await user.click(wallet);
    expect(expanded(wallet)).toBe(true);
    const list = screen.getByRole("list", { name: "Wallet (BTC) accounts" });
    expect(list.id).toBe(wallet.getAttribute("aria-controls"));
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual([
      "Wallet0.50000000 BTC", "Coldcard0.25000000 BTC", "Paper WalletHidden0.01000000 BTC",
    ]);
    await user.click(screen.getByText("0.76000000 BTC")); // the whole line, its figure too
    expect(expanded(wallet)).toBe(false);
    expect(screen.queryByRole("list", { name: "Wallet (BTC) accounts" })).toBeNull();
  });

  it("each exchange's dollars under Exchange (USD), its bitcoin under Exchange (BTC)", async () => {
    const user = userEvent.setup();
    mount(TWO_WALLETS_TWO_EXCHANGES);
    await user.click(lineButton("Exchange (USD)"));
    await user.click(lineButton("Exchange (BTC)"));
    expect(within(screen.getByRole("list", { name: "Exchange (USD) accounts" })).getAllByRole("listitem")
      .map((li) => li.textContent)).toEqual(["Exchange$20.00", "Kraken$0.00"]);
    expect(within(screen.getByRole("list", { name: "Exchange (BTC) accounts" })).getAllByRole("listitem")
      .map((li) => li.textContent)).toEqual(["Exchange0.25000000 BTC", "Kraken0.05000000 BTC"]);
  });

  it("works from the keyboard: Tab to a caret, Enter opens it, Space closes it", async () => {
    const user = userEvent.setup();
    mount(TWO_WALLETS_TWO_EXCHANGES);
    await user.tab();
    expect(document.activeElement).toBe(lineButton("Exchange (USD)"));
    await user.keyboard("{Enter}");
    expect(expanded(lineButton("Exchange (USD)"))).toBe(true);
    await user.keyboard(" ");
    expect(expanded(lineButton("Exchange (USD)"))).toBe(false);
  });

  it("remembers the open lines on this device", async () => {
    const user = userEvent.setup();
    const { unmount } = mount(TWO_WALLETS_TWO_EXCHANGES);
    await user.click(lineButton("Wallet (BTC)"));
    expect(JSON.parse(window.localStorage.getItem(OPEN_LINES_KEY)!)).toEqual(["wallet"]);
    unmount();
    mount(TWO_WALLETS_TWO_EXCHANGES);
    expect(expanded(lineButton("Wallet (BTC)"))).toBe(true);
    expect(expanded(lineButton("Exchange (USD)"))).toBe(false);
  });

  it("opens alpha.1's open Exchange card as both exchange lines, and reads anything else as closed", () => {
    window.localStorage.setItem(OPEN_LINES_KEY, '["exchange"]');
    const { unmount } = mount(TWO_WALLETS_TWO_EXCHANGES);
    expect(expanded(lineButton("Exchange (USD)"))).toBe(true);
    expect(expanded(lineButton("Exchange (BTC)"))).toBe(true);
    unmount();
    window.localStorage.setItem(OPEN_LINES_KEY, "{broken");
    mount(TWO_WALLETS_TWO_EXCHANGES);
    expect(screen.getAllByRole("button").map((b) => b.getAttribute("aria-expanded"))).toEqual(["false", "false", "false"]);
  });

  it("still opens and closes when the browser keeps nothing", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("SecurityError"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("QuotaExceededError"); });
    const user = userEvent.setup();
    mount(TWO_WALLETS_TWO_EXCHANGES);
    await user.click(lineButton("Wallet (BTC)"));
    expect(expanded(lineButton("Wallet (BTC)"))).toBe(true);
  });
});
