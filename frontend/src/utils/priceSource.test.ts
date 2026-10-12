import { describe, expect, it } from "vitest";
import {
  TOR_PLACEHOLDER,
  cannotSave,
  formFromSettings,
  managedBanner,
  payloadFromForm,
  priceFormChanged,
  shownAddress,
  torOffered,
  type NetworkSettingsData,
} from "./priceSource";

const NODE = "http://umbrel.local:3006";
const ONION = "http://mempoolabcdefghijklmnopqrstuvwxyz234567abcdefghijklmnop.onion";
const TOR = "socks5h://127.0.0.1:9050";
const base: NetworkSettingsData = { price_source: "unset", mempool_url: null, mempool_fallback: false, proxy_url: null };

// Every stored choice carries over (plan section 4): the card shows it, and
// saving it unchanged sends exactly what is stored.
const CARRY_OVER: [string, NetworkSettingsData][] = [
  ["not chosen", base],
  ["Nobody (once Off)", { ...base, price_source: "off" }],
  ["Nobody with a leftover address and proxy", { ...base, price_source: "off", mempool_url: NODE, proxy_url: TOR }],
  ["public", { ...base, price_source: "public" }],
  ["public through Tor", { ...base, price_source: "public", proxy_url: TOR }],
  ["Mempool", { ...base, price_source: "mempool", mempool_url: NODE }],
  ["Mempool with its backup through Tor", { ...base, price_source: "mempool", mempool_url: NODE, mempool_fallback: true, proxy_url: TOR }],
  ["an .onion Mempool", { ...base, price_source: "mempool", mempool_url: ONION, proxy_url: TOR }],
];

describe("every stored choice carries over", () => {
  it.each(CARRY_OVER)("%s", (_, saved) => {
    const form = formFromSettings(saved);
    expect(form.source).toBe(saved.price_source === "unset" ? "" : saved.price_source);
    expect(form.tor).toBe(saved.proxy_url !== null);
    expect(priceFormChanged(saved, form)).toBe(false);
    if (saved.price_source !== "unset") {
      expect(payloadFromForm(form)).toEqual({
        price_source: saved.price_source,
        mempool_url: saved.mempool_url,
        mempool_fallback: saved.mempool_fallback,
        proxy_url: saved.proxy_url,
      });
    }
  });
});

describe("the form", () => {
  const saved: NetworkSettingsData = { ...base, price_source: "mempool", mempool_url: NODE };
  const form = formFromSettings(saved);

  it("sees a change to any field, spaces aside", () => {
    expect(priceFormChanged(saved, { ...form, mempoolUrl: ` ${NODE} ` })).toBe(false);
    expect(priceFormChanged(saved, { ...form, source: "public" })).toBe(true);
    expect(priceFormChanged(saved, { ...form, backup: true })).toBe(true);
    expect(priceFormChanged(saved, { ...form, tor: true })).toBe(true);
    expect(priceFormChanged(null, form)).toBe(false);
  });

  it("prefills Tor's usual address and sends it only when ticked", () => {
    const fresh = formFromSettings({ ...base, price_source: "public" });
    expect(fresh.torUrl).toBe(TOR_PLACEHOLDER);
    expect(payloadFromForm(fresh).proxy_url).toBeNull();
    expect(payloadFromForm({ ...fresh, tor: true }).proxy_url).toBe(TOR_PLACEHOLDER);
  });

  it("offers Tor for public sites, your Mempool's backup and an .onion only", () => {
    expect(torOffered({ ...form, source: "public" })).toBe(true);
    expect(torOffered(form)).toBe(false);
    expect(torOffered({ ...form, backup: true })).toBe(true);
    expect(torOffered({ ...form, mempoolUrl: ONION })).toBe(true);
    expect(torOffered({ ...form, source: "off" })).toBe(false);
  });

  it("an .onion goes through Tor even unticked", () => {
    expect(payloadFromForm({ ...form, mempoolUrl: ONION, tor: false }).proxy_url).toBe(TOR_PLACEHOLDER);
    expect(cannotSave({ ...form, mempoolUrl: ONION, torUrl: " " })).toMatch(/through Tor/);
  });

  it("says why it can't save yet", () => {
    expect(cannotSave({ ...form, source: "" })).toMatch(/Choose/);
    expect(cannotSave({ ...form, mempoolUrl: "  " })).toMatch(/address/);
    expect(cannotSave(form)).toBeNull();
    expect(cannotSave({ ...form, source: "off" })).toBeNull();
  });
});

describe("set by the server", () => {
  const startos: NetworkSettingsData = {
    ...base, price_source: "mempool", mempool_url: "http://10.0.3.1:32768", proxy_url: "socks5h://10.0.3.1:9050",
    managed: true, host: "startos",
  };

  it("names where it's changed", () => {
    expect(managedBanner(startos)).toMatch(/Actions › Price Source & Privacy/);
    expect(managedBanner({ ...startos, host: "server" })).toMatch(/BTCTX_PRICE_SOURCE/);
    expect(managedBanner({ ...startos, managed: false })).toBeNull();
  });

  it("never shows StartOS's internal addresses", () => {
    expect(shownAddress(startos, "mempool")).toBe("Mempool on this server");
    expect(shownAddress({ ...startos, mempool_url: null }, "mempool")).toMatch(/isn't installed/);
    expect(shownAddress(startos, "tor")).toBe("Tor on this server");
    expect(shownAddress({ ...startos, host: "server" }, "mempool")).toBe("http://10.0.3.1:32768");
  });
});
