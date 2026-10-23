// Settings' sections (#355): which are open, remembered per browser, and a
// link that opens one.
import { describe, expect, it } from "vitest";
import {
  OPEN_SECTIONS_KEY, SETTINGS_SECTIONS, initiallyOpen, linkedSection, rememberOpen, rememberedOpen, reviewSummary,
  toggled,
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

describe("the open sections", () => {
  it("start all closed in a browser that has none stored", () => {
    expect(rememberedOpen(store())).toEqual([]);
    expect(rememberedOpen(undefined)).toEqual([]);
  });

  it("are remembered for this browser, in the page's order", () => {
    const s = store();
    rememberOpen(s, ["river", "accounts"]);
    expect(rememberedOpen(s)).toEqual(["accounts", "river"]);
    expect(JSON.parse(s.data.get(OPEN_SECTIONS_KEY)!)).toEqual(["river", "accounts"]);
  });

  it("leave out what isn't a section, and anything stored that isn't a list", () => {
    expect(rememberedOpen(store({ [OPEN_SECTIONS_KEY]: '["about", "nope", 3, null]' }))).toEqual(["about"]);
    expect(rememberedOpen(store({ [OPEN_SECTIONS_KEY]: '{"about": true}' }))).toEqual([]);
    expect(rememberedOpen(store({ [OPEN_SECTIONS_KEY]: "not json" }))).toEqual([]);
  });

  it("are all closed when the storage can't be read, and only forgotten when it can't be written", () => {
    expect(rememberedOpen(refusing)).toEqual([]);
    expect(() => rememberOpen(refusing, ["about"])).not.toThrow();
  });

  it("open and close one at a time, others left as they are", () => {
    expect(toggled([], "privacy")).toEqual(["privacy"]);
    expect(toggled(["about", "account"], "privacy")).toEqual(["account", "privacy", "about"]);
    expect(toggled(["account", "privacy"], "privacy")).toEqual(["account"]);
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

  it("opens it beside the remembered ones", () => {
    const s = store({ [OPEN_SECTIONS_KEY]: '["about"]' });
    expect(initiallyOpen(s, "#privacy")).toEqual(["privacy", "about"]);
    expect(initiallyOpen(s, "#about")).toEqual(["about"]);
    expect(initiallyOpen(s, "")).toEqual(["about"]);
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
});
