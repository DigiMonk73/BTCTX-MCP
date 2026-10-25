// @vitest-environment jsdom
// Settings asks Ledger Review again once another section saved what it reads
// (#355, #645): the tax timezone (its times and tax years), Recalculate
// Ledger (the figures it would change), an exchange's 1099-DA switch (its
// "sale may differ" check, exchangeSwitch355.test.tsx). Ledger Review's
// section stays mounted, and otherwise loads only when the page opens.
import "../test/setup";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import { ONE_OF_EACH } from "../test/books";
import type { PastYearWarning } from "../utils/pastYears";
import Settings from "./Settings";

const REVIEW = { total: 0, reminders: 0, checks: [], recalc_error: null, timezone: "UTC" };

const WARNING: PastYearWarning = {
  detail: "This changes the figures of tax year 2025, which you may already have filed. " +
    "Confirm to save it: a copy of your ledger is made first.",
  years: [2025], changes: [], pending: [], recalc_error: null, exact: true, why_not_exact: null,
  timezone: "UTC",
  confirm: "c".repeat(64),
};

function refused(status: number, data: unknown): AxiosError {
  const response = { data, status, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_REQUEST", undefined, undefined, response);
}

interface Answers {
  /** Each review, in turn: what it answers, and when. */
  reviews?: Array<() => Promise<unknown>>;
  put?: () => Promise<unknown>;
  post?: () => Promise<unknown>;
}

async function mount({ reviews = [], put, post }: Answers = {}) {
  window.localStorage.clear(); // every section closed, as a new browser has them
  let asked = 0;
  const get = vi.spyOn(api, "get").mockImplementation(async (url: string) => {
    if (url === "/review") return (reviews[asked++] ?? (async () => ({ data: REVIEW })))();
    if (url === "/accounts/") return { data: ONE_OF_EACH };
    if (url === "/calculations/accounts/balances") return { data: [] };
    if (url === "/settings/tax-timezone") return { data: { timezone: "UTC", source: "setting" } };
    throw new Error(`not in this test: ${url}`);
  });
  vi.spyOn(api, "put").mockImplementation(put ?? (async () => ({ data: { timezone: "Asia/Tokyo", source: "setting" } })));
  vi.spyOn(api, "post").mockImplementation(post ?? (async () => ({ data: { detail: "Recalculated 0 transaction(s)." } })));
  render(<MemoryRouter initialEntries={["/settings"]}><ToastProvider><Settings /></ToastProvider></MemoryRouter>);
  const reviewsAsked = () => get.mock.calls.filter(([url]) => url === "/review").length;
  await waitFor(() => expect(reviewsAsked()).toBe(1));
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Account" }));
  return { user, reviews: reviewsAsked };
}

async function saveTokyo(view: Awaited<ReturnType<typeof mount>>) {
  await screen.findByText("UTC", { selector: "strong" });
  await view.user.selectOptions(screen.getByLabelText("Tax timezone"), "Asia/Tokyo");
  await view.user.click(screen.getByRole("button", { name: "Save" }));
}

/** Whatever was going to happen has: the page's promises and timers run out. */
const settled = () => act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });

describe("Ledger Review, after another section saved", () => {
  it("is asked again once a new tax timezone is saved", async () => {
    const view = await mount();
    await saveTokyo(view);
    await waitFor(() => expect(view.reviews()).toBe(2));
  });

  it("is asked again once Recalculate Ledger has run", async () => {
    const view = await mount();
    await view.user.click(screen.getByRole("button", { name: "Recalculate" }));
    await waitFor(() => expect(view.reviews()).toBe(2));
  });

  it("isn't, when the timezone's past-year warning is cancelled: nothing was saved", async () => {
    const view = await mount({ put: async () => { throw refused(409, WARNING); } });
    await saveTokyo(view);
    const dialog = await screen.findByRole("dialog", { name: "Change an earlier tax year?" });
    await view.user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await settled();
    expect(view.reviews()).toBe(1);
  });

  it("isn't, when Recalculate Ledger fails", async () => {
    const view = await mount({ post: async () => { throw refused(400, { detail: "Ledger not balanced for BTC" }); } });
    await view.user.click(screen.getByRole("button", { name: "Recalculate" }));
    await screen.findByText(/Recalculation failed/);
    await settled();
    expect(view.reviews()).toBe(1);
  });

  it("shows the last review asked for, whichever answer comes last", async () => {
    let first: (value: unknown) => void = () => {};
    const view = await mount({
      reviews: [
        () => new Promise((resolve) => { first = resolve; }), // the page's own, still on its way
        async () => ({ data: REVIEW }), // asked after the save: nothing to review
      ],
    });
    await saveTokyo(view);
    await waitFor(() => expect(view.reviews()).toBe(2));
    await act(async () => first({ data: { ...REVIEW, total: 3 } }));
    await settled();
    expect(screen.getByRole("button", { name: "Ledger Review" }).textContent).toContain("Nothing to review");
  });
});
