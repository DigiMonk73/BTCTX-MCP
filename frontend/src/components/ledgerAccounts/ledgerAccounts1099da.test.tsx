// @vitest-environment jsdom
// B7b-4's proving test: each exchange's "This exchange sends me a Form 1099-DA"
// switch (spec 5.9), on its bitcoin account's row, with its help text word for
// word. It goes through the past-year warning (5.8; B6c's stub on the draft
// branch): a 409 carrying `confirm` asks the owner with the server's sentence in
// the warning's dialog (B6b), and only Save anyway sends the same change again
// with ?confirm=<fingerprint>.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { TWO_BALANCES, TWO_OF_EACH } from "../../test/accountBooks";
import { CONFIRM, renderSettings, type RenderedSettings } from "../../test/renderSettings";
import { pastYearsWarning } from "../../utils/pastYears";
import { AxiosError, type AxiosResponse } from "axios";

const SWITCH = "This exchange sends me a Form 1099-DA";
const HELP = "An exchange in the US sends one for your sales from 2025; one outside the US usually doesn't. " +
  "It decides the Form 8949 box, not the gain.";
const WARNING = "This changes the figures of tax years 2024 and 2025, which you may already have filed. " +
  "Confirm to save it: a copy of your ledger is made first.";

const row = (name: string) => screen.getByRole("listitem", { name });
const theSwitch = (name: string) => within(row(name)).getByRole("checkbox", { name: SWITCH });
const writes = (s: RenderedSettings) => s.requests.slice(2).filter((r) => r.method !== "get");
// The warning's fingerprint, as B7b's helper in utils/ledgerAccounts.ts gave it (B6b: utils/pastYears.ts)
const fingerprintOf = (error: unknown) => pastYearsWarning(error)?.confirm ?? null;
const dialog = () => screen.getByRole("dialog", { name: "Change an earlier tax year?" });

function axiosError(status: number, data: object): AxiosError {
  const response = { data, status, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError("failed", "ERR_BAD_RESPONSE", undefined, undefined, response);
}

afterEach(() => vi.restoreAllMocks());

describe("pastYearsWarning's fingerprint (utils/pastYears.ts)", () => {
  it("is the fingerprint of a 409 that asks to confirm", () => {
    expect(fingerprintOf(axiosError(409, { detail: WARNING, years: [2024, 2025], confirm: "abc" }))).toBe("abc");
  });

  it("is null for any other refusal or error", () => {
    expect(fingerprintOf(axiosError(409, { detail: "This account has transactions…" }))).toBeNull();
    expect(fingerprintOf(axiosError(400, { detail: "x", confirm: "abc" }))).toBeNull();
    expect(fingerprintOf(new Error("network"))).toBeNull();
    expect(fingerprintOf(undefined)).toBeNull();
  });
});

describe("the switch (components/ledgerAccounts/AccountRow.tsx)", () => {
  it("is on each exchange's bitcoin account's row, checked from the book, with its help", async () => {
    const book = TWO_OF_EACH.map((a) => (a.exchange_id === 2 ? { ...a, sends_1099da: false } : a));
    await renderSettings({ book, balances: TWO_BALANCES });
    expect(theSwitch("Exchange BTC")).toBeChecked();
    expect(theSwitch("Kraken BTC")).not.toBeChecked();
    expect(row("Kraken BTC")).toHaveTextContent(HELP);
    expect(screen.getAllByRole("checkbox", { name: SWITCH })).toHaveLength(2);
    for (const name of ["Bank", "Wallet", "Exchange USD", "Kraken USD", "Old Wallet"]) {
      expect(within(row(name)).queryByRole("checkbox")).toBeNull();
    }
  });

  it("with no earlier year to change, sends sends_1099da once and shows it saved", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await s.user.click(theSwitch("Kraken BTC"));
    await s.settle();
    expect(writes(s)).toEqual([{ method: "put", url: "/accounts/103", body: { sends_1099da: false } }]);
    expect(s.requests.at(-1)).toEqual({ method: "get", url: "/accounts/" });
    expect(theSwitch("Kraken BTC")).not.toBeChecked();
    expect(screen.getByRole("status")).toHaveTextContent("Saved.");
  });

  it("with earlier years: asks with the server's sentence, and Yes sends it again confirmed", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES, pastYears: [2024, 2025] });
    await s.user.click(theSwitch("Exchange BTC"));
    await s.settle();
    expect(dialog()).toHaveAccessibleDescription(WARNING);
    await s.user.click(within(dialog()).getByRole("button", { name: "Save anyway (a copy is made first)" }));
    await s.settle();
    expect(writes(s)).toEqual([
      { method: "put", url: "/accounts/4", body: { sends_1099da: false } },
      { method: "put", url: "/accounts/4", body: { sends_1099da: false }, params: { confirm: CONFIRM } },
    ]);
    expect(theSwitch("Exchange BTC")).not.toBeChecked();
    expect(screen.getByRole("status")).toHaveTextContent("Saved.");
  });

  it("with earlier years: Cancel sends nothing more, keeps the switch and says so", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES, pastYears: [2025] });
    await s.user.click(theSwitch("Exchange BTC"));
    await s.settle();
    await s.user.click(within(dialog()).getByRole("button", { name: "Cancel" }));
    await s.settle();
    expect(writes(s)).toHaveLength(1);
    expect(theSwitch("Exchange BTC")).toBeChecked();
    expect(screen.getByRole("status")).toHaveTextContent("Not changed.");
  });

  it("another refusal is shown unchanged, without asking", async () => {
    const detail = "Only an exchange's accounts have this setting.";
    const s = await renderSettings({
      book: TWO_OF_EACH, balances: TWO_BALANCES,
      refuse: { "put /accounts/103": { status: 400, body: { detail } } },
    });
    await s.user.click(theSwitch("Kraken BTC"));
    await s.settle();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent(detail);
  });

  it("a newly added exchange starts with the switch on", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await s.user.click(screen.getByRole("button", { name: "Add an exchange" }));
    await s.user.type(screen.getByRole("textbox", { name: "Nickname" }), "Bitstamp");
    await s.user.click(screen.getByRole("button", { name: "Add" }));
    await s.settle();
    expect(theSwitch("Bitstamp BTC")).toBeChecked();
  });
});
