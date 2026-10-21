// B6b-9's proving test: the past-year warning's 409 read from a write's error
// (spec 5.8), its words, a write's ?confirm=, and the years whose adds the owner
// said not to ask about again while the page is open.
import { AxiosError, type AxiosResponse } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import {
  addsSkipAsking, askForAddsAgain, confirmed, itemText, pastYearsWarning, stopAskingForAdds, yearsText,
  type PastYearsItem,
} from "./pastYears";

function axiosError(status: number, data: unknown): AxiosError {
  const response = { data, status, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError("failed", "ERR_BAD_RESPONSE", undefined, undefined, response);
}

const ITEM: PastYearsItem = {
  id: 7, date: "2025-03-01 12:00", type: "Withdrawal", purpose: "Spent", source: null, amount: "0.50000000",
  unit: "BTC", accounts: ["Wallet"], change: "gain 10000.00 -> 5000.00.", years: [2025],
};

afterEach(() => askForAddsAgain());

describe("pastYearsWarning", () => {
  it("reads a 409 that carries a fingerprint and its years", () => {
    const body = { detail: "This changes…", years: [2024, 2025], changes: [ITEM], pending: [], recalc_error: null,
      confirm: "abc" };
    expect(pastYearsWarning(axiosError(409, body))).toEqual(body);
  });

  it("fills what an older body leaves out (the 1099-DA switch's stub has no recalc_error)", () => {
    expect(pastYearsWarning(axiosError(409, { detail: "x", years: [2025], confirm: "abc" }))).toEqual({
      detail: "x", years: [2025], changes: [], pending: [], recalc_error: null, confirm: "abc",
    });
  });

  it("is null for any other refusal or error", () => {
    expect(pastYearsWarning(axiosError(409, { detail: "This account has transactions…" }))).toBeNull();
    expect(pastYearsWarning(axiosError(409, { detail: "Delete All", transactions: 3, confirm: 5 }))).toBeNull();
    expect(pastYearsWarning(axiosError(409, { detail: "x", confirm: "abc" }))).toBeNull(); // no years
    expect(pastYearsWarning(axiosError(400, { detail: "x", years: [2025], confirm: "abc" }))).toBeNull();
    expect(pastYearsWarning(new Error("network"))).toBeNull();
    expect(pastYearsWarning(undefined)).toBeNull();
  });
});

describe("the words", () => {
  it.each([
    [[2025], "2025"],
    [[2024, 2025], "2024 and 2025"],
    [[2023, 2024, 2025], "2023, 2024 and 2025"],
  ])("years %j are %s", (years, text) => {
    expect(yearsText(years)).toBe(text);
  });

  it("a row reads as Ledger Review's items do", () => {
    expect(itemText(ITEM)).toBe("2025-03-01 12:00 · Withdrawal (Spent) · 0.50000000 BTC · Wallet: gain 10000.00 -> 5000.00.");
    expect(itemText({ ...ITEM, type: "Transfer", purpose: null, unit: "USD", amount: "500.00",
      accounts: ["Bank", "Exchange USD"], change: "Deleted." })).toBe(
      "2025-03-01 12:00 · Transfer · $500.00 · Bank → Exchange USD: Deleted.");
    expect(itemText({ ...ITEM, accounts: [] })).toBe(
      "2025-03-01 12:00 · Withdrawal (Spent) · 0.50000000 BTC: gain 10000.00 -> 5000.00.");
  });
});

describe("confirmed", () => {
  it("is ?confirm=<fingerprint> for a write sent again, nothing for the first", () => {
    expect(confirmed("abc")).toEqual({ params: { confirm: "abc" } });
    expect(confirmed(undefined)).toBeUndefined();
    expect(confirmed("")).toBeUndefined();
  });
});

describe("adds not asked about again", () => {
  it("only for the years ticked, all of them, until the page asks again", () => {
    expect(addsSkipAsking([2025])).toBe(false);
    stopAskingForAdds([2025]);
    expect(addsSkipAsking([2025])).toBe(true);
    expect(addsSkipAsking([2024, 2025])).toBe(false);
    stopAskingForAdds([2024]);
    expect(addsSkipAsking([2024, 2025])).toBe(true);
    expect(addsSkipAsking([])).toBe(false);
    askForAddsAgain();
    expect(addsSkipAsking([2025])).toBe(false);
  });
});
