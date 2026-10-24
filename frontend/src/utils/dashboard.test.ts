import { describe, expect, it } from "vitest";
import {
  accountTotals, gainClass, kindCards, noPriceReason, openCardsAfter, priceSourceShort, priceSourceWords, readOpenCards,
  toggleLabel,
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

describe("kindCards: Bank, Exchange and Wallet as P7's mockups have them (#356)", () => {
  it("one of each: three cards of one row each, no toggle", () => {
    const cards = kindCards(ONE_OF_EACH);
    expect(cards.map((c) => [c.title, c.usd, c.btc, c.rows.length])).toEqual([
      ["Bank", 1500.25, 0, 1], ["Exchange", 20, 0.25, 1], ["Wallet", 0, 0.5, 1]]);
    expect(cards.map((c) => toggleLabel(c, false))).toEqual([null, null, null]);
  });

  it("each exchange is one row, its dollars and bitcoin side by side, by its name", () => {
    const exchange = kindCards(TWO_OF_EACH)[1];
    expect(exchange.rows).toEqual([
      { key: "exchange-1", name: "Exchange", usd: 20, btc: 0.25, hidden: false },
      { key: "exchange-2", name: "Kraken", usd: 0, btc: 0.05, hidden: false },
    ]);
    expect([exchange.usd, exchange.btc]).toEqual([20, 0.3]);
  });

  it("a hidden account with a zero balance is left out; one holding coins stays, marked", () => {
    const wallet = kindCards(TWO_OF_EACH)[2];
    expect(wallet.rows.map((r) => [r.name, r.btc, r.hidden])).toEqual([
      ["Wallet", 0.5, false], ["Cold Storage", 0.25, false], ["Paper Wallet", 0.01, true]]);
    expect(wallet.btc).toBe(0.76);
  });

  it("a hidden exchange is left out only when both its accounts are zero", () => {
    const hidden = { ...KRAKEN, hidden: true };
    const cards = kindCards([...ONE_OF_EACH, balance(102, "Kraken USD", "exchange", "USD", "5.00", hidden),
      balance(103, "Kraken BTC", "exchange", "BTC", "0", hidden)]);
    expect(cards[1].rows.map((r) => [r.name, r.hidden])).toEqual([["Exchange", false], ["Kraken", true]]);
    const empty = kindCards([...ONE_OF_EACH, balance(102, "Kraken USD", "exchange", "USD", "0", hidden),
      balance(103, "Kraken BTC", "exchange", "BTC", "0", hidden)]);
    expect(empty[1].rows.map((r) => r.name)).toEqual(["Exchange"]);
  });

  it("a renamed Wallet stays on the Wallet card, by its new name", () => {
    const renamed = ONE_OF_EACH.map((b) => (b.account_id === 2 ? { ...b, name: "Coldcard" } : b));
    const wallet = kindCards(renamed)[2];
    expect([wallet.title, wallet.btc, wallet.rows[0].name]).toEqual(["Wallet", 0.5, "Coldcard"]);
  });

  it("the fee accounts are on no card", () => {
    const names = kindCards(TWO_OF_EACH).flatMap((c) => c.rows.map((r) => r.name));
    expect(names).not.toContain("BTC Fees");
    expect(names).not.toContain("USD Fees");
  });

  it("a card with more than one row offers its toggle, with the count", () => {
    const [bank, exchange, wallet] = kindCards(TWO_OF_EACH);
    expect([toggleLabel(bank, false), toggleLabel(exchange, false), toggleLabel(wallet, false)])
      .toEqual(["Show accounts (2)", "Show accounts (2)", "Show accounts (3)"]);
    expect(toggleLabel(wallet, true)).toBe("Hide accounts");
  });

  it("a card with no account at all shows zero and no toggle", () => {
    const cards = kindCards([]);
    expect(cards.map((c) => [c.title, c.usd, c.btc, c.rows.length, toggleLabel(c, false)])).toEqual([
      ["Bank", 0, 0, 0, null], ["Exchange", 0, 0, 0, null], ["Wallet", 0, 0, 0, null]]);
  });
});

describe("the open cards, remembered per browser (P7)", () => {
  it("reads what was stored, keeping only the three kinds, in the cards' order", () => {
    expect(readOpenCards('["wallet","exchange","nope",3]')).toEqual(["exchange", "wallet"]);
  });

  it("starts closed with nothing stored or something unreadable", () => {
    expect(readOpenCards(null)).toEqual([]);
    expect(readOpenCards("{not json")).toEqual([]);
    expect(readOpenCards('{"wallet":true}')).toEqual([]);
  });

  it("opens and closes one card, leaving the others", () => {
    expect(openCardsAfter(["bank"], "wallet")).toEqual(["bank", "wallet"]);
    expect(openCardsAfter(["bank", "wallet"], "bank")).toEqual(["wallet"]);
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
