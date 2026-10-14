import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { TOR_REFUSED, clock, historyLine, olderValuesNote, statusLine, type PriceStatus, type StatusContext, mempoolProblem } from "./priceStatus";

const history: PriceStatus["history"] = {
  until: "2026-10-12T09:00Z", first_year: 2013, shipped: false, years_total: 14, years_done: 0,
  state: "not_allowed", failed_at: null, mismatched: [],
};
const base: PriceStatus = {
  source: "mempool", managed: false, invalid: false, waiting: false, host: "mac", last_ok: null, last_problem: null,
  history,
};
const ctx: StatusContext = { backup: false, tor: false };
const T1 = "2026-10-12T19:02:00Z"; // 2:02 pm in Chicago
const T2 = "2026-10-12T19:04:00Z";

// Times are this device's clock (#260): here, a computer in Chicago
const testsTz = process.env.TZ;
beforeAll(() => { process.env.TZ = "America/Chicago"; });
afterAll(() => { process.env.TZ = testsTz; });

describe("the status line", () => {
  it("says when nothing is contacted", () => {
    expect(statusLine({ ...base, source: "unset" }, ctx)).toEqual({ tone: "idle", text: "Not chosen yet: nothing is contacted." });
    expect(statusLine({ ...base, source: "off" }, ctx).text).toMatch(/^Fully offline: nothing is contacted/);
    expect(statusLine({ ...base, source: "off", invalid: true, managed: true }, ctx)).toEqual({
      tone: "warning", text: "This server's price settings aren't valid, so nothing is contacted.",
    });
  });

  it("names the source and the time of the last price, on this device's clock", () => {
    expect(clock(T1)).toBe("2:02 pm");
    process.env.TZ = "Asia/Tokyo";
    expect(clock(T1)).toBe("4:02 am"); // whatever the tax timezone: the device's own clock (#260)
    process.env.TZ = "America/Chicago";
    expect(statusLine({ ...base, last_ok: { at: T1, from: "mempool" } }, ctx)).toEqual({
      tone: "ok", text: "Newer prices from your Mempool. Last price 2:02 pm.",
    });
    const pub = { ...base, source: "public" as const, last_ok: { at: T1, from: "kraken" } };
    expect(statusLine(pub, { ...ctx, tor: true }).text).toBe("Newer prices from public price sites, through Tor. Last price 2:02 pm.");
    expect(statusLine({ ...base, source: "public" }, ctx).text).toBe("Newer prices will come from public price sites.");
  });

  it("says your Mempool didn't answer, and what to do", () => {
    const down = { ...base, last_ok: { at: T1, from: "mempool" }, last_problem: { at: T2, what: "mempool_no_answer" as const } };
    const line = statusLine(down, ctx);
    expect(line.tone).toBe("warning");
    expect(line.text).toBe(
      "Your Mempool didn't answer at 2:04 pm. Type newer values meanwhile, or tick \"If it can't answer, ask public price sites\".",
    );
    expect(statusLine({ ...down, managed: true }, ctx).text).toBe("Your Mempool didn't answer at 2:04 pm. Type newer values meanwhile.");
    // the backup already ticked (its answer not in yet): not asked to tick it
    expect(statusLine(down, { ...ctx, backup: true }).text).toBe("Your Mempool didn't answer at 2:04 pm. Type newer values meanwhile.");
  });

  it("#178: an untrusted certificate is named, and when the backup answers it says so", () => {
    const untrusted = { ...base, last_problem: { at: T1, what: "mempool_untrusted_certificate" as const } };
    expect(statusLine(untrusted, ctx).text).toBe(
      "Your Mempool's certificate isn't trusted (a private one, like StartOS's home-network address), so BitcoinTX " +
        "can't use it. There's no newer price: use its http:// or .onion address instead, or on StartOS choose My Mempool on this server.",
    );
    // #188: at a home-network address, the card offers to trust it
    expect(statusLine(untrusted, { ...ctx, trustable: true }).text).toMatch(
      /There's no newer price until you trust it: if it's your own server, use Trust this server below\.$/,
    );
    expect(mempoolProblem(untrusted)).toBe("mempool_untrusted_certificate");
    const backup = { ...untrusted, last_ok: { at: T2, from: "kraken" } };
    const line = statusLine(backup, { ...ctx, backup: true });
    expect(line.tone).toBe("warning");
    expect(line.text).toMatch(/certificate isn't trusted/);
    expect(line.text).toMatch(/Public price sites answered instead at 2:04 pm\.$/);
    expect(line.text).not.toMatch(/from your Mempool/);
  });

  it("names Mempool missing on StartOS, and Tor or public sites not answering", () => {
    const missing = { ...base, managed: true, host: "startos" as const, last_problem: { at: T1, what: "mempool_missing" as const } };
    expect(statusLine(missing, ctx).text).toBe(
      "Mempool isn't installed on this server yet. Install and start it, or choose another source in StartOS.",
    );
    const tor = { ...base, source: "public" as const, last_problem: { at: T1, what: "tor_no_answer" as const } };
    expect(statusLine(tor, { ...ctx, tor: true }).text).toBe("Public price sites didn't answer through Tor at 2:02 pm. Is Tor running?");
    const both = {
      ...base, last_ok: { at: T1, from: "mempool" }, last_problem: { at: T2, what: "public_no_answer" as const },
      last_mempool_problem: { at: T2, what: "mempool_untrusted_certificate" as const },
    };
    // Review of #180: the Mempool's reason isn't lost when the backup fails too
    expect(statusLine(both, { ...ctx, backup: true }).text).toMatch(
      /^Your Mempool's certificate isn't trusted .* Public price sites didn't answer either, at 2:04 pm\.$/,
    );
  });

  it("a price after the problem clears it", () => {
    const back = { ...base, last_ok: { at: T2, from: "mempool" }, last_problem: { at: T1, what: "mempool_no_answer" as const } };
    expect(statusLine(back, ctx).tone).toBe("ok");
  });
});

describe("waiting for the owner to confirm (#145, 2.9)", () => {
  it("says nothing is contacted until then, whatever the choice", () => {
    for (const source of ["public", "mempool", "off"] as const) {
      expect(statusLine({ ...base, source, waiting: true }, ctx)).toEqual({
        tone: "idle", text: "Waiting for you to confirm: nothing is contacted until you do.",
      });
    }
  });
});

describe("re-check of #180: the backup answered once, then both failed", () => {
  const T0 = "2026-10-12T19:00:00Z";
  const state = {
    ...base,
    last_ok: { at: T0, from: "kraken" },
    last_mempool_problem: { at: T1, what: "mempool_untrusted_certificate" as const },
    last_problem: { at: T2, what: "public_no_answer" as const },
  };

  it("never says the public sites answered when they just failed, and keeps the Mempool's reason", () => {
    const line = statusLine(state, { ...ctx, backup: true });
    expect(line.text).toMatch(/^Your Mempool's certificate isn't trusted .* Public price sites didn't answer either, at 2:04 pm\.$/);
    expect(line.text).not.toMatch(/answered instead/);
  });

  it("through Tor, asks whether Tor is running", () => {
    const tor = { ...state, last_problem: { at: T2, what: "tor_no_answer" as const } };
    expect(statusLine(tor, { ...ctx, backup: true, tor: true }).text).toMatch(
      /Public price sites didn't answer through Tor either, at 2:04 pm\. Is Tor running\?$/,
    );
  });

  it("the backup answering after a failure keeps the Mempool's reason", () => {
    const later = { ...state, last_problem: state.last_mempool_problem, last_ok: { at: T2, from: "kraken" } };
    expect(statusLine(later, { ...ctx, backup: true }).text).toMatch(
      /^Your Mempool's certificate isn't trusted .* Public price sites answered instead at 2:04 pm\.$/,
    );
  });
});

describe("the hourly history's line (#145, the amendment's A)", () => {
  const h = (over: Partial<PriceStatus["history"]>) => ({ ...base, history: { ...history, ...over } });

  it("before a choice: where it will come from, and that no request names a date", () => {
    expect(historyLine({ ...h({}), source: "unset" }, ctx)?.text).toBe(
      "Hourly prices, 2013 to Oct 12, 2026: downloaded once from Bitstamp when you choose Public price sites, or " +
        "My own Mempool with its backup, each year checked against a fingerprint that comes with BitcoinTX. " +
        "Nothing in the download names your dates.",
    );
  });

  it("downloading, with its progress, through Tor when it is", () => {
    const line = historyLine(h({ state: "downloading", years_done: 6 }), { ...ctx, tor: true });
    expect(line?.text).toMatch(/^Downloading the hourly history from Bitstamp through Tor: 6 of 14 years, each checked\./);
    expect(line?.progress).toEqual({ done: 6, total: 14 });
  });

  it("done, failed, a year that didn't match, and a choice that doesn't allow it", () => {
    expect(historyLine(h({ state: "complete", years_done: 14 }), ctx)).toMatchObject({
      tone: "ok", text: "Hourly prices, 2013 to Oct 12, 2026: downloaded and checked. They work offline from now on, whatever you choose.",
    });
    expect(historyLine(h({ state: "failed" }), { ...ctx, tor: true })?.text).toMatch(
      /through Tor: is Tor running\? It's tried again when BitcoinTX next needs it or restarts, at least 10 minutes later\./,
    );
    expect(historyLine(h({ state: "failed", refused: true }), { ...ctx, tor: true })).toEqual({
      tone: "warning", text: `The hourly history didn't download. ${TOR_REFUSED}`,
    });
    expect(TOR_REFUSED).toMatch(/^Through Tor, Bitstamp currently refuses BitcoinTX's requests, so the hourly history and past prices don't download/);
    expect(historyLine(h({ state: "failed", refused: true }), ctx)?.text).toMatch(/didn't download: Bitstamp refused it\./);
    expect(historyLine(h({ state: "waiting", mismatched: [2019] }), ctx)?.text).toBe(
      "Bitstamp's prices for 2019 didn't match BitcoinTX's fingerprint, so 2019 uses the day's price. " +
        "Tried again a day later, when BitcoinTX next needs it or restarts.",
    );
    expect(historyLine(h({ state: "waiting", mismatched: [2019, 2020] }), ctx)?.text).toMatch(/so 2019, 2020 use the day's price/);
    expect(historyLine({ ...h({}), source: "off" }, ctx)?.text).toBe(
      "The hourly history (2013 to Oct 12, 2026) needs a one-time download from Bitstamp, which your choice doesn't allow.",
    );
  });

  it("review of #186: chosen but not downloaded (yet, or a failure long ago) never reads as not chosen", () => {
    expect(historyLine({ ...h({ state: "waiting" }), source: "public" }, ctx)?.text).toBe(
      "Hourly prices, 2013 to Oct 12, 2026: not downloaded yet. BitcoinTX downloads the rest from Bitstamp " +
        "when BitcoinTX next needs it or restarts. Meanwhile those values use the day's price.",
    );
    expect(historyLine({ ...h({ state: "waiting", years_done: 6 }), source: "mempool" }, ctx)?.text).toMatch(
      /: 6 of 14 years downloaded and checked\./,
    );
    // a year that didn't match, then Nobody chosen: the choice's line, not "tried again"
    expect(historyLine({ ...h({ state: "not_allowed", mismatched: [2019] }), source: "off" }, ctx)?.text).toMatch(
      /which your choice doesn't allow\.$/,
    );
  });

  it("re-check of #186: with the server's settings invalid, no line blames the choice", () => {
    expect(historyLine({ ...h({ state: "not_allowed" }), source: "public", invalid: true }, ctx)).toBeNull();
  });

  it("built in, once Bitstamp agrees: the approved line", () => {
    expect(historyLine(h({ shipped: true }), ctx)?.text).toBe(
      "Built in: every hourly price from 2013 to Oct 12, 2026. Works offline, nothing to set.",
    );
  });

  it("says what your Mempool alone, or Nobody, means for older values, until the history is here", () => {
    expect(olderValuesNote("mempool", false, history)).toMatch(/^It has hourly prices only from when it began recording/);
    expect(olderValuesNote("mempool", true, history)).toBeNull();
    expect(olderValuesNote("off", false, history)).toMatch(/choose Public price sites until the download finishes, then Nobody/);
    expect(olderValuesNote("off", false, { ...history, state: "complete" })).toBeNull();
    expect(olderValuesNote("public", false, history)).toBeNull();
  });
});
