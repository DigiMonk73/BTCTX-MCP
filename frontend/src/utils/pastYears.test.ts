// The past-year warning's pure part (2.0 spec 5.8, #352, #353): which 409 is
// the warning, its years in words, its changes under their years, the years
// the page keeps quiet for adds, and what an import's preview says of its
// rows dated in earlier years.
import { AxiosError, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import {
  addsQuietFor,
  byTaxYears,
  forgetQuietYears,
  importNote,
  keepAddsQuiet,
  pastYearWarning,
  taxYearsLabel,
  yearsInWords,
  type PastYearChange,
} from "./pastYears";

function failed(status: number, data: unknown): AxiosError {
  const response = { data, status, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_REQUEST", undefined, undefined, response);
}

const change = (date: string, years: number[]): PastYearChange => ({
  id: 1, date, type: "Sell", purpose: null, source: null, amount: "0.1", unit: "BTC",
  realized_gain_usd: "1.00", issue: "Changes with this save.", change: "gain 1.00 -> 2.00.", years,
});

const WARNING = {
  detail: "This changes the figures of tax years 2024 and 2025, which you may already have filed.",
  years: [2024, 2025],
  changes: [change("2024-06-01 12:00", [2024])],
  pending: [],
  recalc_error: null,
  exact: true,
  why_not_exact: null,
  timezone: "UTC",
  coins_chosen: null,
  confirm: "ab".repeat(32),
};

describe("pastYearWarning", () => {
  it("reads the warning out of its 409", () => {
    expect(pastYearWarning(failed(409, WARNING))).toEqual(WARNING);
  });

  it("is null for the other 409s and every other failure", () => {
    expect(pastYearWarning(failed(409, { detail: "BitcoinTX was updated: reload the page." }))).toBeNull();
    expect(pastYearWarning(failed(409, { detail: "x", transactions: 3, first_year: 2024, last_year: 2025 }))).toBeNull();
    expect(pastYearWarning(failed(409, { ...WARNING, confirm: 7 }))).toBeNull();
    expect(pastYearWarning(failed(409, undefined))).toBeNull();
    expect(pastYearWarning(failed(422, WARNING))).toBeNull();
    expect(pastYearWarning(new Error("no answer"))).toBeNull();
    expect(pastYearWarning(null)).toBeNull();
  });

  it("an answer missing its lists or its exactness reads as empty and exact", () => {
    const read = pastYearWarning(failed(409, { detail: "Dated in 2024.", confirm: "c" }));
    expect(read).toEqual({
      detail: "Dated in 2024.", years: [], changes: [], pending: [], recalc_error: null,
      exact: true, why_not_exact: null, timezone: null, coins_chosen: null, confirm: "c",
    });
  });

  it("keeps the zone its rows' dates are in (#737)", () => {
    expect(pastYearWarning(failed(409, { ...WARNING, timezone: "Asia/Tokyo" }))?.timezone).toBe("Asia/Tokyo");
  });

  it("the date-based warning keeps why it isn't exact", () => {
    const read = pastYearWarning(failed(409, { ...WARNING, changes: [], exact: false, why_not_exact: "Too slow." }));
    expect([read?.exact, read?.why_not_exact, read?.changes]).toEqual([false, "Too slow.", []]);
  });
});

describe("yearsInWords and taxYearsLabel", () => {
  it("say one, two or more years, oldest first, each once", () => {
    expect(yearsInWords([2025])).toBe("2025");
    expect(yearsInWords([2025, 2024])).toBe("2024 and 2025");
    expect(yearsInWords([2023, 2025, 2024, 2024])).toBe("2023, 2024 and 2025");
    expect(yearsInWords([])).toBe("");
  });

  it("a heading names the tax year or years", () => {
    expect(taxYearsLabel([2025])).toBe("Tax year 2025");
    expect(taxYearsLabel([2024, 2024])).toBe("Tax year 2024");
    expect(taxYearsLabel([2024, 2025])).toBe("Tax years 2024 and 2025");
    expect(taxYearsLabel([])).toBe("");
  });
});

describe("byTaxYears", () => {
  it("groups the changes by their years, in the server's order, a moved row once", () => {
    const a = change("2024-02-01 12:00", [2024]);
    const b = change("2024-09-01 12:00", [2024, 2025]);
    const c = change("2024-10-01 12:00", [2024]);
    const d = change("2025-03-01 12:00", [2025]);
    expect(byTaxYears([a, b, c, d])).toEqual([
      { label: "Tax year 2024", items: [a, c] },
      { label: "Tax years 2024 and 2025", items: [b] },
      { label: "Tax year 2025", items: [d] },
    ]);
    expect(byTaxYears([])).toEqual([]);
  });
});

describe("the years kept quiet for adds", () => {
  afterEach(forgetQuietYears);

  it("asks until a year is kept quiet, then only for the years that aren't", () => {
    expect(addsQuietFor([2025])).toBe(false);
    keepAddsQuiet([2025]);
    expect(addsQuietFor([2025])).toBe(true);
    expect(addsQuietFor([2024, 2025])).toBe(false);
    expect(addsQuietFor([2024])).toBe(false);
    keepAddsQuiet([2024]);
    expect(addsQuietFor([2024, 2025])).toBe(true);
  });

  it("a warning naming no year is always asked", () => {
    keepAddsQuiet([2025]);
    expect(addsQuietFor([])).toBe(false);
  });

  it("forgets them all, as a reload does", () => {
    keepAddsQuiet([2024, 2025]);
    forgetQuietYears();
    expect(addsQuietFor([2025])).toBe(false);
  });
});

describe("importNote", () => {
  it("names the earlier tax years an import's rows are dated in, before it asks", () => {
    expect(importNote([2025])).toBe("Rows dated in tax year 2025 can change the figures of that year and later " +
      "ones you may already have filed: BitcoinTX shows what changes, and asks, before it imports them.");
    expect(importNote([2025, 2024])).toBe("Rows dated in tax years 2024 and 2025 can change the figures of those " +
      "years and later ones you may already have filed: BitcoinTX shows what changes, and asks, before it " +
      "imports them.");
  });

  it("says nothing for rows of this year, or a preview from before 2.0", () => {
    expect(importNote([])).toBeNull();
    expect(importNote(undefined)).toBeNull();
  });
});
