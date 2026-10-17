import { describe, expect, it } from "vitest";
import { answeredWords, changeLabel, questionOpen, refusedWords } from "./historyWithoutTor";
import type { NetworkSettingsData } from "./priceSource";
import type { PriceStatus } from "./priceStatus";

const TOR = "socks5h://127.0.0.1:9050";

function saved(patch: Partial<NetworkSettingsData> = {}): NetworkSettingsData {
  return {
    price_source: "public", mempool_url: null, mempool_fallback: false, proxy_url: TOR,
    history_without_tor: { answer: null, at: null, via: null }, ...patch,
  };
}

function status(patch: Partial<PriceStatus> = {}): PriceStatus {
  return {
    source: "public", managed: false, invalid: false, waiting: false, host: "server",
    last_ok: null, last_problem: null, bitstamp_refused: true,
    history: {
      until: "2026-10-12T23:00Z", first_year: 2013, shipped: false, years_total: 14, years_done: 0,
      state: "failed", failed_at: null, refused: true, mismatched: [],
    },
    ...patch,
  };
}

describe("the question about the price history without Tor (#241)", () => {
  it("is open once Bitstamp refused through Tor, until it's answered", () => {
    expect(questionOpen(saved(), status())).toBe(true);
    expect(questionOpen(saved(), status({ bitstamp_refused: false }))).toBe(false); // Tor down isn't a refusal
    expect(questionOpen(saved({ proxy_url: null }), status())).toBe(false);
    expect(questionOpen(saved({ history_without_tor: { answer: "no", at: null, via: null } }), status())).toBe(false);
    expect(questionOpen(saved(), status({ waiting: true }))).toBe(false);
    expect(questionOpen(saved(), status({ invalid: true }))).toBe(false);
    expect(questionOpen(null, status())).toBe(false);
    expect(questionOpen(saved(), null)).toBe(false);
  });

  it("says what the refusal keeps from downloading, as the history stands (the review's 3)", () => {
    expect(refusedWords(status())).toBe("The hourly history didn't download: through Tor, Bitstamp refuses BitcoinTX's requests.");
    const held = status();
    held.history = { ...held.history, state: "complete", years_done: 14, refused: false };
    expect(refusedWords(held)).toBe("Through Tor, Bitstamp refuses BitcoinTX's requests, so newer hours and past days don't download.");
  });

  it("is open while the server sets the choice too: the answer is the owner's", () => {
    expect(questionOpen(saved({ managed: true }), status({ managed: true }))).toBe(true);
  });

  it("shows the recorded answer, when and where, while Tor is on", () => {
    const yes = saved({ history_without_tor: { answer: "yes", at: "2026-10-16T15:00:00Z", via: "dashboard" } });
    expect(answeredWords(yes)).toBe(
      "Bitstamp's price history without Tor: yes, since Oct 16, 2026 (answered on the Dashboard). " +
        "Only its fixed history blocks go without Tor; the live price and everything else stay on Tor.",
    );
    const no = saved({ history_without_tor: { answer: "no", at: "2026-10-16T15:00:00Z", via: "settings" } });
    expect(answeredWords(no)).toMatch(/^Bitstamp's price history without Tor: no, since Oct 16, 2026 \(answered in Settings\)\. Everything stays on Tor/);
    expect(answeredWords({ ...yes, proxy_url: null })).toBeNull();
    expect(answeredWords(saved())).toBeNull();
    expect([changeLabel("yes"), changeLabel("no")]).toEqual(["Keep it on Tor instead", "Download it without Tor"]);
  });
});
