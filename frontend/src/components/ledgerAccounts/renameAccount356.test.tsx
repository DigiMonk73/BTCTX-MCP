// @vitest-environment jsdom
// Settings' Rename (#356, 2.0 spec 5.9): a row's new name goes to
// PUT /api/accounts/{id} {name}, then the book and the balances are read
// again; the server's refusal is shown in its words; an exchange's row says
// what its two accounts become. The click-through is in
// e2e/screens-renames-356.e2e.ts.
import "../../test/setup";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { describe, expect, it, vi } from "vitest";
import api from "../../api";
import { ONE_OF_EACH } from "../../test/books";
import LedgerAccounts from "../LedgerAccounts";

const BOOK = ONE_OF_EACH.map((a) => ({ ...a, in_use: true }));

function refused(status: number, detail: string): AxiosError {
  const response = { data: { detail }, status, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_REQUEST", undefined, undefined, response);
}

/** The section on BOOK with `name`'s details open; each PUT answered by `put`. */
async function mount(name: string, put: () => Promise<unknown>) {
  vi.spyOn(api, "get").mockResolvedValue({ data: [] });
  const sent = vi.spyOn(api, "put").mockImplementation(put);
  const reload = vi.fn(async () => {});
  render(<LedgerAccounts book={BOOK} failed={false} reload={reload} />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: new RegExp(`^${name}\\b`) }));
  const details = screen.getByRole("region", { name });
  return { sent, reload, user, details, field: within(details).getByLabelText("Name") as HTMLInputElement,
    rename: within(details).getByRole("button", { name: "Rename" }) };
}

describe("Settings' Rename", () => {
  it("starts on the account's name with nothing to send, sends the new one, then reads the book again", async () => {
    const view = await mount("Wallet", async () => ({ data: {} }));
    expect(view.field.value).toBe("Wallet");
    expect(view.rename).toHaveProperty("disabled", true);
    await view.user.clear(view.field);
    await view.user.type(view.field, "Coldcard");
    expect(view.rename).toHaveProperty("disabled", false);
    await view.user.click(view.rename);
    await waitFor(() => expect(view.reload).toHaveBeenCalledTimes(1));
    expect(view.sent.mock.calls.map(([url, body]) => [url, body])).toEqual([["/accounts/2", { name: "Coldcard" }]]);
  });

  it("sends from the keyboard too", async () => {
    const view = await mount("Bank", async () => ({ data: {} }));
    await view.user.clear(view.field);
    await view.user.type(view.field, "Checking{Enter}");
    await waitFor(() => expect(view.sent).toHaveBeenCalledWith("/accounts/1", { name: "Checking" }));
  });

  it("shows a refusal in the server's words and keeps what was typed", async () => {
    const words = "'Bank' always means your first bank in files (CSV, River, BitcoinTX 1.x): choose another name.";
    const view = await mount("Wallet", async () => { throw refused(400, words); });
    await view.user.clear(view.field);
    await view.user.type(view.field, "Bank");
    await view.user.click(view.rename);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", words);
    expect(view.field.value).toBe("Bank");
    expect(view.reload).not.toHaveBeenCalled();
  });

  it("an exchange's row renames the exchange, and says what its two accounts become", async () => {
    const view = await mount("Exchange", async () => ({ data: {} }));
    expect(view.field.value).toBe("Exchange");
    await view.user.clear(view.field);
    await view.user.type(view.field, "Coinbase");
    expect(within(view.details).getByText(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'Coinbase USD' and 'Coinbase BTC'.",
    )).toBeTruthy();
    await view.user.click(view.rename);
    await waitFor(() => expect(view.sent).toHaveBeenCalledWith("/accounts/4", { name: "Coinbase" }));
  });

  it("says how files name a renamed account", async () => {
    const view = await mount("Wallet", async () => ({ data: {} }));
    expect(within(view.details).getByText(/^A CSV file names accounts as they're named when you import it/))
      .toBeTruthy();
  });
});
