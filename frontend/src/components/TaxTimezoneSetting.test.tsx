// @vitest-environment jsdom
// Settings' tax timezone through the past-year warning (2.0 spec 5.8, #353):
// a Save the server answers with the warning's 409 is saved only once the
// owner confirms it, by the same request sent again with its confirm; Cancel
// saves nothing and keeps the timezone in use.
import "../test/setup";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosRequestConfig, type AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider, type Toast } from "../contexts/ToastContext";
import ToastLog from "../test/ToastLog";
import type { PastYearWarning } from "../utils/pastYears";
import TaxTimezoneSetting from "./TaxTimezoneSetting";

const WARNING: PastYearWarning = {
  detail: "This changes the figures of tax years 2025 and 2026, which you may already have filed. " +
    "Confirm to save it: a copy of your ledger is made first.",
  years: [2025, 2026],
  changes: [{
    id: 3, date: "2026-01-01 03:00", type: "Sell", purpose: null, source: null, amount: "0.25", unit: "BTC",
    realized_gain_usd: "14750.00", issue: "Changes with this save.", change: "Tax year 2026 -> 2025.",
    years: [2025, 2026],
  }],
  pending: [],
  recalc_error: null,
  exact: true,
  why_not_exact: null,
  confirm: "c".repeat(64),
};

function refused(data: unknown): AxiosError {
  const response = { data, status: 409, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError("Request failed with status code 409", "ERR_BAD_REQUEST", undefined, undefined, response);
}

/** Settings' row on a server whose timezone is UTC; each Save answered by `put`. */
async function mount(put: (config?: AxiosRequestConfig) => unknown) {
  vi.spyOn(api, "get").mockResolvedValue({ data: { timezone: "UTC", source: "setting" } });
  const sent = vi.spyOn(api, "put").mockImplementation(async (_url, _body, config) => ({ data: put(config) }));
  let toasts: Toast[] = [];
  render(
    <ToastProvider>
      <TaxTimezoneSetting />
      <ToastLog onToasts={(t) => { toasts = t; }} />
    </ToastProvider>,
  );
  const user = userEvent.setup();
  await screen.findByText("UTC", { selector: "strong" });
  await user.selectOptions(screen.getByLabelText("Tax timezone"), "Asia/Tokyo");
  await user.click(screen.getByRole("button", { name: "Save" }));
  const dialog = await screen.findByRole("dialog", { name: "Change an earlier tax year?" });
  return { sent, user, dialog, toasts: () => toasts.map((t) => t.message) };
}

/** The confirm a request was sent with, if any. */
const confirmOf = (config?: AxiosRequestConfig): unknown => (config?.params as { confirm?: string } | undefined)?.confirm;

/** Refused with the warning until it comes back with its confirm. */
const warnsUntilConfirmed = (config?: AxiosRequestConfig) => {
  if (confirmOf(config) !== WARNING.confirm) throw refused(WARNING);
  return { timezone: "Asia/Tokyo", source: "setting" };
};

describe("Settings' tax timezone that changes an earlier tax year", () => {
  it("asks, with the years and what changes, then saves it with its confirm", async () => {
    const view = await mount(warnsUntilConfirmed);
    expect(within(view.dialog).getByText(WARNING.detail)).toBeTruthy();
    expect(within(view.dialog).getByText(/Tax year 2026 -> 2025\./)).toBeTruthy();
    await view.user.click(within(view.dialog).getByRole("button", { name: "Save anyway (a copy is made first)" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(view.sent.mock.calls.map(([url, body, config]) => [url, body, confirmOf(config)])).toEqual([
      ["/settings/tax-timezone", { timezone: "Asia/Tokyo", chosen: true }, undefined],
      ["/settings/tax-timezone", { timezone: "Asia/Tokyo", chosen: true }, WARNING.confirm],
    ]);
    expect(view.toasts()).toEqual(["Tax timezone set to Asia/Tokyo. Gains were recalculated."]);
    expect(screen.getByText("Asia/Tokyo", { selector: "strong" })).toBeTruthy();
  });

  it("saves nothing when the owner cancels, and keeps the timezone in use", async () => {
    const view = await mount(warnsUntilConfirmed);
    await view.user.click(within(view.dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(view.sent).toHaveBeenCalledTimes(1);
    expect(view.toasts()).toEqual([]);
    expect(screen.getByText("UTC", { selector: "strong" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toHaveProperty("disabled", false);
  });
});
