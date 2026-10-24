// @vitest-environment jsdom
// River's import through the past-year warning (2.0 spec 5.8, #353): its
// preview names the earlier tax years its new rows are dated in, and an
// import the server answers with the warning's 409 is made only once the
// owner confirms it, one confirm for the file; Cancel imports nothing and
// keeps the preview as it was.
import "../test/setup";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosRequestConfig, type AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider, type Toast } from "../contexts/ToastContext";
import ToastLog from "../test/ToastLog";
import { importNote, type PastYearWarning } from "../utils/pastYears";
import RiverImport from "./RiverImport";

const PREVIEW: RiverPreviewResponse = {
  success: true, total_rows: 1, new_count: 1, matched_count: 0, discrepancy_count: 0,
  proposals: [{
    row_number: 2, date: "2025-03-05T12:00:00Z", river_tag: "Buy", type: "Buy", from_account: "Bank",
    to_account: "Exchange BTC", amount: "0.0003", cost_basis_usd: "25.00", type_choices: ["Buy"],
    funding_choices: ["Bank", "Exchange USD"], basis_autofilled: false, status: "new",
  }],
  errors: [], warnings: [], past_years: [2025],
};

const WARNING: PastYearWarning = {
  detail: "This changes the figures of tax year 2025, which you may already have filed. " +
    "Confirm to save it: a copy of your ledger is made first.",
  years: [2025],
  changes: [{
    id: null, date: "2025-03-05 12:00", type: "Buy", purpose: null, source: null, amount: "0.0003", unit: "BTC",
    realized_gain_usd: null, issue: "Changes with this save.", change: "Added: cost of the lots it made 25.00.",
    years: [2025],
  }],
  pending: [],
  recalc_error: null,
  exact: true,
  why_not_exact: null,
  confirm: "d".repeat(64),
};

function refused(data: unknown): AxiosError {
  const response = { data, status: 409, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError("Request failed with status code 409", "ERR_BAD_REQUEST", undefined, undefined, response);
}

/** The confirm a request was sent with, if any. */
const confirmOf = (config?: AxiosRequestConfig): unknown => (config?.params as { confirm?: string } | undefined)?.confirm;

/** The import's answer: the warning until it comes back with its confirm. */
const warnsUntilConfirmed = (config?: AxiosRequestConfig) => {
  if (confirmOf(config) !== WARNING.confirm) throw refused(WARNING);
  return { success: true, imported_count: 1, skipped_existing: 0, message: "Imported 1 transaction(s)." };
};

/** River's card with a file previewed, then Import clicked (the browser's own question answered yes). */
async function previewAndImport() {
  const sent = vi.spyOn(api, "post").mockImplementation(async (url, _body, config) => ({
    data: url === "/import/river/preview" ? PREVIEW : warnsUntilConfirmed(config),
  }));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  let toasts: Toast[] = [];
  render(
    <ToastProvider>
      <RiverImport onPreviewShown={() => undefined} />
      <ToastLog onToasts={(t) => { toasts = t; }} />
    </ToastProvider>,
  );
  const user = userEvent.setup();
  await user.upload(screen.getByLabelText("River CSV file"), new File(["River"], "river.csv", { type: "text/csv" }));
  await user.click(screen.getByRole("button", { name: "Preview" }));
  const note = await screen.findByRole("note");
  await user.click(screen.getByRole("button", { name: "Import 1 Transaction(s)" }));
  const dialog = await screen.findByRole("dialog", { name: "Change an earlier tax year?" });
  const imports = () => sent.mock.calls.filter(([url]) => url === "/import/river/execute");
  return { note, dialog, user, imports, toasts: () => toasts.map((t) => t.message) };
}

describe("River's import of rows that change an earlier tax year", () => {
  it("names the years in its preview, asks, then imports the file with its one confirm", async () => {
    const view = await previewAndImport();
    expect(view.note.textContent).toBe(importNote([2025]));
    expect(within(view.dialog).getByText(WARNING.detail)).toBeTruthy();
    await view.user.click(within(view.dialog).getByRole("button", { name: "Save anyway (a copy is made first)" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    const [first, again] = view.imports();
    expect(again[1]).toEqual(first[1]); // the same rows
    expect([confirmOf(first[2]), confirmOf(again[2])]).toEqual([undefined, WARNING.confirm]);
    expect(view.toasts()).toEqual(["Imported 1 transaction(s)."]);
    expect(screen.queryByRole("button", { name: "Import 1 Transaction(s)" })).toBeNull(); // done: the card resets
  });

  it("imports nothing when the owner cancels, and keeps the preview", async () => {
    const view = await previewAndImport();
    await view.user.click(within(view.dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(view.imports()).toHaveLength(1);
    expect(view.toasts()).toEqual([]);
    expect(screen.getByRole("button", { name: "Import 1 Transaction(s)" })).toHaveProperty("disabled", false);
  });
});
