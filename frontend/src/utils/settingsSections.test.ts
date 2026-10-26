// Settings' sections (#355): one open at a time, remembered per browser, and
// a link that opens one.
import { describe, expect, it } from "vitest";
import {
  OPEN_SECTION_KEY, SETTINGS_SECTIONS, aiSummary, initiallyOpen, linkedSection, rememberOpen, rememberedOpen,
  reviewSummary, toggled,
} from "./settingsSections";

function store(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    data,
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
  };
}

const refusing = {
  getItem: () => { throw new Error("SecurityError"); },
  setItem: () => { throw new Error("QuotaExceededError"); },
};

describe("the open section", () => {
  it("is none in a browser that has none stored", () => {
    expect(rememberedOpen(store())).toBeNull();
    expect(rememberedOpen(undefined)).toBeNull();
  });

  it("is remembered for this browser, and forgotten once closed", () => {
    const s = store();
    rememberOpen(s, "river");
    expect(rememberedOpen(s)).toBe("river");
    expect(s.data.get(OPEN_SECTION_KEY)).toBe('"river"');
    rememberOpen(s, null);
    expect(rememberedOpen(s)).toBeNull();
  });

  it("is none when what's stored isn't a section", () => {
    expect(rememberedOpen(store({ [OPEN_SECTION_KEY]: '"nope"' }))).toBeNull();
    expect(rememberedOpen(store({ [OPEN_SECTION_KEY]: '["about"]' }))).toBeNull();
    expect(rememberedOpen(store({ [OPEN_SECTION_KEY]: "not json" }))).toBeNull();
  });

  it("is none when the storage can't be read, and only forgotten when it can't be written", () => {
    expect(rememberedOpen(refusing)).toBeNull();
    expect(() => rememberOpen(refusing, "about")).not.toThrow();
  });

  it("is one at a time: opening one closes the one before; pressing the open one closes it", () => {
    expect(toggled(null, "privacy")).toBe("privacy");
    expect(toggled("account", "privacy")).toBe("privacy");
    expect(toggled("privacy", "privacy")).toBeNull();
  });

  it("every section has an id of its own", () => {
    expect(new Set(SETTINGS_SECTIONS).size).toBe(SETTINGS_SECTIONS.length);
    expect(SETTINGS_SECTIONS.slice(0, 2)).toEqual(["account", "accounts"]); // after the Account section (5.9)
  });
});

describe("a link to a section", () => {
  it("names it after the #", () => {
    expect(linkedSection("#privacy")).toBe("privacy");
    expect(linkedSection("")).toBeNull();
    expect(linkedSection("#")).toBeNull();
    expect(linkedSection("#no-such-section")).toBeNull();
  });

  it("opens it in place of the remembered one", () => {
    const s = store({ [OPEN_SECTION_KEY]: '"about"' });
    expect(initiallyOpen(s, "#privacy")).toBe("privacy");
    expect(initiallyOpen(s, "")).toBe("about");
    expect(initiallyOpen(store(), "")).toBeNull();
  });
});

describe("Ledger Review's summary", () => {
  it("says how the review stands, so a closed section hides nothing", () => {
    expect(reviewSummary(undefined)).toBe("Checking…");
    expect(reviewSummary(null)).toBe("The review could not be loaded");
    expect(reviewSummary({ total: 0, reminders: 0 })).toBe("Nothing to review");
    expect(reviewSummary({ total: 0, reminders: 2 })).toBe("Nothing looks wrong");
    expect(reviewSummary({ total: 1, reminders: 0 })).toBe("1 transaction to check");
    expect(reviewSummary({ total: 3, reminders: 1 })).toBe("3 transactions to check");
  });

  it("says so when Recalculate Ledger would stop, which no count includes", () => {
    const stops = "Ledger not balanced for BTC";
    expect(reviewSummary({ total: 0, reminders: 0, recalc_error: stops })).toBe("Recalculate Ledger would stop: see why");
    expect(reviewSummary({ total: 2, reminders: 0, recalc_error: stops }))
      .toBe("2 transactions to check; Recalculate Ledger would stop");
    expect(reviewSummary({ total: 0, reminders: 0, recalc_error: null })).toBe("Nothing to review");
  });
});

describe("Connect an AI Assistant's summary", () => {
  it("words the key by edition (#724), and names none before it's known", () => {
    const what = "Optional and off until you turn it on: an AI app that reads your ledger and enters transactions";
    expect(aiSummary(true)).toBe(`${what}, with a key BitcoinTX keeps for it`);
    expect(aiSummary(false)).toBe(`${what}, with a key you create`);
    expect(aiSummary(undefined)).toBe(what);
  });
});
