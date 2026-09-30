import { describe, expect, it } from "vitest";
import { networkSettingsChanged, type NetworkSettingsData } from "./priceSource";

const saved: NetworkSettingsData = {
  price_source: "mempool",
  mempool_url: "http://umbrel.local:3006",
  mempool_fallback: false,
  proxy_url: null,
};
const form = { source: "mempool" as const, mempoolUrl: "http://umbrel.local:3006", fallback: false, proxyUrl: "" };

describe("networkSettingsChanged", () => {
  it("is unchanged when the form shows what is saved, spaces aside", () => {
    expect(networkSettingsChanged(saved, form)).toBe(false);
    expect(networkSettingsChanged(saved, { ...form, mempoolUrl: " http://umbrel.local:3006 ", proxyUrl: "  " })).toBe(false);
  });

  it("sees a change to any field", () => {
    expect(networkSettingsChanged(saved, { ...form, source: "public" })).toBe(true);
    expect(networkSettingsChanged(saved, { ...form, mempoolUrl: "http://node.local:3006" })).toBe(true);
    expect(networkSettingsChanged(saved, { ...form, fallback: true })).toBe(true);
    expect(networkSettingsChanged(saved, { ...form, proxyUrl: "socks5h://127.0.0.1:9050" })).toBe(true);
  });

  it("has nothing to save before the settings load or a source is chosen", () => {
    expect(networkSettingsChanged(null, form)).toBe(false);
    expect(networkSettingsChanged({ ...saved, price_source: "unset" }, { ...form, source: "" })).toBe(false);
  });
});
