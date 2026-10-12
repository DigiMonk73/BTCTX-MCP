import { describe, expect, it } from "vitest";
import { clock, statusLine, type PriceStatus, type StatusContext } from "./priceStatus";

const history: PriceStatus["history"] = {
  until: "2026-10-12T09:00Z", first_year: 2013, shipped: false, years_total: 14, years_done: 0,
  state: "not_allowed", failed_at: null, mismatched: [],
};
const base: PriceStatus = {
  source: "mempool", managed: false, invalid: false, host: "mac", last_ok: null, last_problem: null, history,
};
const ctx: StatusContext = { backup: false, tor: false, timezone: "America/Chicago" };
const T1 = "2026-10-12T19:02:00Z"; // 2:02 pm in Chicago
const T2 = "2026-10-12T19:04:00Z";

describe("the status line", () => {
  it("says when nothing is contacted", () => {
    expect(statusLine({ ...base, source: "unset" }, ctx)).toEqual({ tone: "idle", text: "Not chosen yet: nothing is contacted." });
    expect(statusLine({ ...base, source: "off" }, ctx).text).toMatch(/^Fully offline: nothing is contacted/);
    expect(statusLine({ ...base, source: "off", invalid: true, managed: true }, ctx)).toEqual({
      tone: "warning", text: "This server's price settings aren't valid, so nothing is contacted.",
    });
  });

  it("names the source and the time of the last price, in the tax timezone", () => {
    expect(clock(T1, "America/Chicago")).toBe("2:02 pm");
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
  });

  it("#178: an untrusted certificate is named, and when the backup answers it says so", () => {
    const untrusted = { ...base, last_problem: { at: T1, what: "mempool_untrusted_certificate" as const } };
    expect(statusLine(untrusted, ctx).text).toBe(
      "Your Mempool's certificate isn't trusted (a private one, like StartOS's home-network address), so BitcoinTX " +
        "can't use it. There's no newer price: use its http:// or .onion address instead, or on StartOS choose My Mempool on this server.",
    );
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
