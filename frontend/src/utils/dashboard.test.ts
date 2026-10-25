import { describe, expect, it } from "vitest";
import {
  OPEN_LINES_KEY, accountTotals, balanceLines, gainClass, listsAccounts, noPriceReason, openLinesAfter, priceSourceShort,
  priceSourceWords, readOpenLines, type BalanceLine,
} from "./dashboard";

type Extra = Partial<Pick<AccountBalance, "exchange_id" | "exchange" | "hidden">>;

/** One row of GET /calculations/accounts/balances (2.0 spec 5.13: with its kind, exchange and hidden). */
const balance = (
  account_id: number, name: string, kind: AccountBalance["kind"], currency: string, value: number | string,
  extra: Extra = {},
): AccountBalance => ({ account_id, name, kind, currency, balance: value, exchange_id: null, exchange: null,
  hidden: false, ...extra });

const EXCHANGE = { exchange_id: 1, exchange: "Exchange" };
const KRAKEN = { exchange_id: 2, exchange: "Kraken" };

/** A 1.x ledger's six accounts. */
const ONE_OF_EACH = [
  balance(1, "Bank", "bank", "USD", "1500.25"),
  balance(2, "Wallet", "wallet", "BTC", "0.50000000"),
  balance(3, "Exchange USD", "exchange", "USD", 20, EXCHANGE),
  balance(4, "Exchange BTC", "exchange", "BTC", "0.25000000", EXCHANGE),
  balance(5, "BTC Fees", "fee", "BTC", "0.00010000"),
  balance(6, "USD Fees", "fee", "USD", "12.00"),
];

/** Two banks, three wallets (one hidden and empty, one hidden holding coins) and two exchanges. */
const TWO_OF_EACH = [
  ...ONE_OF_EACH,
  balance(100, "Credit Union", "bank", "USD", "250.00"),
  balance(101, "Cold Storage", "wallet", "BTC", "0.25000000"),
  balance(104, "Old Wallet", "wallet", "BTC", "0.00000000", { hidden: true }),
  balance(105, "Paper Wallet", "wallet", "BTC", "0.01000000", { hidden: true }),
  balance(102, "Kraken USD", "exchange", "USD", "0.00", KRAKEN),
  balance(103, "Kraken BTC", "exchange", "BTC", "0.05000000", KRAKEN),
];

describe("accountTotals", () => {
  it("adds up each kind and the BTC, leaving out the fee accounts by kind", () => {
    expect(accountTotals(ONE_OF_EACH))
      .toEqual({ bank: 1500.25, exchangeUsd: 20, exchangeBtc: 0.25, wallet: 0.5, totalBtc: 0.75 });
  });

  it("adds every account of a kind, hidden ones too (2.0 spec 5.13)", () => {
    expect(accountTotals(TWO_OF_EACH))
      .toEqual({ bank: 1750.25, exchangeUsd: 20, exchangeBtc: 0.3, wallet: 0.76, totalBtc: 1.06 });
  });

  it("goes by kind, never by name: renamed accounts count the same", () => {
    const renamed = ONE_OF_EACH.map((b) => ({ ...b, name: `${b.name} renamed`, exchange: b.exchange && "Coinbase" }));
    expect(accountTotals(renamed)).toEqual(accountTotals(ONE_OF_EACH));
  });

  it("leaves out a fee account however it's named, and an account of no kind", () => {
    const odd = [balance(9, "Network fees", "fee", "BTC", "1"), { ...balance(99, "x", "fee", "BTC", "2"), kind: null }];
    expect(accountTotals([...ONE_OF_EACH, ...odd]).totalBtc).toBe(0.75);
  });

  it("skips a balance that isn't a number", () => {
    expect(accountTotals([balance(2, "Wallet", "wallet", "BTC", NaN), balance(4, "Exchange BTC", "exchange", "BTC", "0.1",
      EXCHANGE)])).toEqual({ bank: 0, exchangeUsd: 0, exchangeBtc: 0.1, wallet: 0, totalBtc: 0.1 });
  });

  it("is all zero with no accounts", () => {
    expect(accountTotals([])).toEqual({ bank: 0, exchangeUsd: 0, exchangeBtc: 0, wallet: 0, totalBtc: 0 });
  });
});

const labels = (lines: BalanceLine[]) => lines.map((l) => l.label);
const listed = (line: BalanceLine) => line.accounts.map((a) => [a.name, a.amount, a.hidden]);
const lineOf = (lines: BalanceLine[], key: BalanceLine["key"]) => lines.find((l) => l.key === key)!;

describe("balanceLines: Portfolio Overview's lines by kind, as 1.x has them (#674)", () => {
  it("one of each: 1.x's four lines in its order, each with its one account and no caret", () => {
    const lines = balanceLines(ONE_OF_EACH);
    expect(lines.map((l) => [l.label, l.currency, l.total, l.accounts.length])).toEqual([
      ["Bank (USD)", "USD", 1500.25, 1], ["Exchange (USD)", "USD", 20, 1],
      ["Exchange (BTC)", "BTC", 0.25, 1], ["Wallet (BTC)", "BTC", 0.5, 1]]);
    expect(lines.map(listsAccounts)).toEqual([false, false, false, false]);
  });

  it("each exchange's dollars under Exchange (USD) and its bitcoin under Exchange (BTC), by the exchange's name", () => {
    const lines = balanceLines(TWO_OF_EACH);
    expect(listed(lineOf(lines, "exchangeUsd"))).toEqual([["Exchange", 20, false], ["Kraken", 0, false]]);
    expect(listed(lineOf(lines, "exchangeBtc"))).toEqual([["Exchange", 0.25, false], ["Kraken", 0.05, false]]);
    expect(listsAccounts(lineOf(lines, "exchangeUsd"))).toBe(true);
    expect(listsAccounts(lineOf(lines, "exchangeBtc"))).toBe(true);
  });

  it("a hidden account holding nothing is left out; one still holding something is listed, marked", () => {
    const wallet = lineOf(balanceLines(TWO_OF_EACH), "wallet");
    expect(listed(wallet)).toEqual([["Wallet", 0.5, false], ["Cold Storage", 0.25, false], ["Paper Wallet", 0.01, true]]);
    expect(wallet.total).toBe(0.76);
  });

  it("a hidden exchange is left out of a line where it holds nothing in that line's currency", () => {
    const hidden = { ...KRAKEN, hidden: true };
    const lines = balanceLines([...ONE_OF_EACH, balance(102, "Kraken USD", "exchange", "USD", "5.00", hidden),
      balance(103, "Kraken BTC", "exchange", "BTC", "0", hidden)]);
    expect(listed(lineOf(lines, "exchangeUsd"))).toEqual([["Exchange", 20, false], ["Kraken", 5, true]]);
    expect(listed(lineOf(lines, "exchangeBtc"))).toEqual([["Exchange", 0.25, false]]);
    expect(listsAccounts(lineOf(lines, "exchangeBtc"))).toBe(false);
  });

  it("a caret only where there's something to list: more than one account, or a hidden one still holding something", () => {
    const [bank, exchangeUsd, exchangeBtc, wallet] = balanceLines(TWO_OF_EACH);
    expect([bank, exchangeUsd, exchangeBtc, wallet].map(listsAccounts)).toEqual([true, true, true, true]);
    // Your only bank hidden with dollars left in it: the line says so when opened
    const hiddenBank = ONE_OF_EACH.map((b) => (b.account_id === 1 ? { ...b, hidden: true } : b));
    expect(listsAccounts(lineOf(balanceLines(hiddenBank), "bank"))).toBe(true);
    // A second wallet hidden and empty: nothing more to list
    const emptyHidden = [...ONE_OF_EACH, balance(104, "Old Wallet", "wallet", "BTC", "0", { hidden: true })];
    expect(listsAccounts(lineOf(balanceLines(emptyHidden), "wallet"))).toBe(false);
  });

  it("the listed amounts add up exactly to the line's total, in cents and in sats", () => {
    const cents = (usd: number) => Math.round(usd * 100);
    const sats = (btc: number) => Math.round(btc * 1e8);
    const odd = [...TWO_OF_EACH, balance(106, "Savings", "bank", "USD", "0.10"), balance(107, "Brokerage", "bank", "USD", "0.20"),
      balance(108, "Hot Wallet", "wallet", "BTC", "0.00000001")];
    for (const line of balanceLines(odd)) {
      const unit = line.currency === "USD" ? cents : sats;
      expect(line.accounts.reduce((sum, a) => sum + unit(a.amount), 0), line.label).toBe(unit(line.total));
    }
    expect(lineOf(balanceLines(odd), "bank").total).toBeCloseTo(1750.55, 9);
  });

  it("the totals are accountTotals', line by line", () => {
    const totals = accountTotals(TWO_OF_EACH);
    expect(balanceLines(TWO_OF_EACH).map((l) => l.total))
      .toEqual([totals.bank, totals.exchangeUsd, totals.exchangeBtc, totals.wallet]);
  });

  it("a renamed Wallet stays on Wallet (BTC), by its new name", () => {
    const renamed = ONE_OF_EACH.map((b) => (b.account_id === 2 ? { ...b, name: "Coldcard" } : b));
    expect(listed(lineOf(balanceLines(renamed), "wallet"))).toEqual([["Coldcard", 0.5, false]]);
  });

  it("the fee accounts are on no line", () => {
    const names = balanceLines(TWO_OF_EACH).flatMap((l) => l.accounts.map((a) => a.name));
    expect(names).not.toContain("BTC Fees");
    expect(names).not.toContain("USD Fees");
  });

  it("no account at all: the four lines at zero, no caret", () => {
    const lines = balanceLines([]);
    expect(labels(lines)).toEqual(["Bank (USD)", "Exchange (USD)", "Exchange (BTC)", "Wallet (BTC)"]);
    expect(lines.map((l) => [l.total, l.accounts.length, listsAccounts(l)])).toEqual([
      [0, 0, false], [0, 0, false], [0, 0, false], [0, 0, false]]);
  });
});

describe("the open lines, remembered on this device (#674)", () => {
  it("reads what was stored, keeping only the four lines, in the card's order", () => {
    expect(readOpenLines('["wallet","exchangeBtc","nope",3]')).toEqual(["exchangeBtc", "wallet"]);
  });

  it("reads alpha.1's open cards: Bank and Wallet stay open, Exchange opens both exchange lines", () => {
    expect(OPEN_LINES_KEY).toBe("btctx.dashboard.openCards");
    expect(readOpenLines('["exchange","wallet"]')).toEqual(["exchangeUsd", "exchangeBtc", "wallet"]);
    expect(readOpenLines('["bank"]')).toEqual(["bank"]);
  });

  it("starts closed with nothing stored or something unreadable", () => {
    expect(readOpenLines(null)).toEqual([]);
    expect(readOpenLines("{not json")).toEqual([]);
    expect(readOpenLines('{"wallet":true}')).toEqual([]);
    expect(readOpenLines("null")).toEqual([]);
  });

  it("opens and closes one line, leaving the others", () => {
    expect(openLinesAfter(["bank"], "wallet")).toEqual(["bank", "wallet"]);
    expect(openLinesAfter(["bank", "wallet"], "bank")).toEqual(["wallet"]);
  });
});

describe("gainClass", () => {
  it("colours a gain and a loss, and not zero", () => {
    expect(gainClass(12.5)).toBe("text-gain");
    expect(gainClass(-0.01)).toBe("text-loss");
    expect(gainClass(0)).toBe("");
  });
});

describe("the price's source and why there's none (#145)", () => {
  it("names public sites, through Tor when it is, and your Mempool", () => {
    expect(priceSourceWords("kraken", true)).toBe("From public price sites (Kraken, through Tor)");
    expect(priceSourceWords("bitstamp")).toBe("From public price sites (Bitstamp)");
    expect(priceSourceWords("mempool", true)).toBe("From your Mempool");
  });

  it("tells invalid server settings apart from Nobody", () => {
    expect(noPriceReason(503, "This server's price settings aren't valid: BTCTX_TOR_PROXY_URL")).toBe("invalid");
    expect(noPriceReason(503, "Price lookups are off")).toBe("off");
  });

  it("the sidebar's short form: the site, through Tor when it is, or your Mempool (#208)", () => {
    expect(priceSourceShort("kraken", true)).toBe("Kraken, through Tor");
    expect(priceSourceShort("bitstamp")).toBe("Bitstamp");
    expect(priceSourceShort("mempool", true)).toBe("Your Mempool");
    expect(priceSourceShort(undefined)).toBeNull();
  });

  it("asks about Tor only when no public site could be reached through it, never for a refusal (#208, #241)", () => {
    // backend/services/bitcoin.py, _first_public, word for word: every site unreachable through
    // the proxy (test_network_settings.py pins the words this matches)
    expect(noPriceReason(502, "No public site answered for the BTC price: none could be reached through the proxy "
      + "for public sites. If that's Tor, is it running? (On StartOS: start the Tor service.)")).toBe("tor");
    // Reached, but no price: a refusal (Bitstamp's 403 to Tor's exits) or a bad answer
    expect(noPriceReason(502, "No public site answered for the BTC price.")).toBe("none");
    expect(noPriceReason(502, undefined)).toBe("none");
    expect(noPriceReason(undefined, undefined)).toBe("none");
  });
});
