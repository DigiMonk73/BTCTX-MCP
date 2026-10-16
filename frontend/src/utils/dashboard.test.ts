import { describe, expect, it } from "vitest";
import { accountTotals, gainClass, noPriceReason, priceSourceShort, priceSourceWords } from "./dashboard";

const balance = (account_id: number, name: string, currency: string, value: number | string): AccountBalance => ({
  account_id, name, currency, balance: value,
});

describe("accountTotals", () => {
  it("shows each account and adds up the BTC, leaving out the fee accounts", () => {
    expect(accountTotals([
      balance(1, "Bank", "USD", "1500.25"),
      balance(2, "Wallet", "BTC", "0.50000000"),
      balance(3, "Exchange USD", "USD", 20),
      balance(4, "Exchange BTC", "BTC", "0.25000000"),
      balance(5, "BTC Fees", "BTC", "0.00010000"),
      balance(6, "USD Fees", "USD", "12.00"),
    ])).toEqual({ bank: 1500.25, exchangeUsd: 20, exchangeBtc: 0.25, wallet: 0.5, totalBtc: 0.75 });
  });

  it("skips a balance that isn't a number", () => {
    expect(accountTotals([balance(2, "Wallet", "BTC", NaN), balance(4, "Exchange BTC", "BTC", "0.1")]))
      .toEqual({ bank: 0, exchangeUsd: 0, exchangeBtc: 0.1, wallet: 0, totalBtc: 0.1 });
  });

  it("is all zero with no accounts", () => {
    expect(accountTotals([])).toEqual({ bank: 0, exchangeUsd: 0, exchangeBtc: 0, wallet: 0, totalBtc: 0 });
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
    // backend/services/bitcoin.py, _first_public: every site unreachable through the proxy
    expect(noPriceReason(502, "No public site answered for the live price: none could be reached through the proxy "
      + "for public sites. If that's Tor, is it running? (On StartOS: start the Tor service.)")).toBe("tor");
    // Reached, but no price: a refusal (Bitstamp's 403 to Tor's exits) or a bad answer
    expect(noPriceReason(502, "No public site answered for the live price.")).toBe("none");
    expect(noPriceReason(502, undefined)).toBe("none");
    expect(noPriceReason(undefined, undefined)).toBe("none");
  });
});
