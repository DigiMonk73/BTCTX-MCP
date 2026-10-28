// @vitest-environment jsdom
// Settings' Delete asks in BitcoinTX's own dialog (#651), as Delete All does,
// never the browser's confirm box: it names the account (an exchange: both
// its accounts) and says only an account with no transactions can be
// deleted. Cancel and Escape send nothing and give the keyboard back to
// Delete, under StrictMode too and after a click that focused nothing (Safari);
// the dialog's Delete sends one request, saying so while it runs. The
// click-through is in
// e2e/settings-accounts-355.e2e.ts.
import "../../test/setup";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import React from "react";
import { beforeEach, expect, it, vi } from "vitest";
import api from "../../api";
import { ONE_OF_EACH } from "../../test/books";
import { forgetAccounts } from "../../utils/useAccounts";
import { useSettingsAccounts } from "../../utils/useSettingsAccounts";
import LedgerAccounts from "../LedgerAccounts";

const UNUSED = { sends_1099da: null, hidden: false, in_use: false };
const BOOK: AccountBook = [
  ...ONE_OF_EACH,
  { ...UNUSED, id: 100, name: "Coldcard", kind: "wallet", currency: "BTC", exchange_id: null, exchange: null },
  { ...UNUSED, id: 101, name: "Kraken USD", kind: "exchange", currency: "USD", exchange_id: 2, exchange: "Kraken",
    sends_1099da: true },
  { ...UNUSED, id: 102, name: "Kraken BTC", kind: "exchange", currency: "BTC", exchange_id: 2, exchange: "Kraken",
    sends_1099da: true },
  // An exchange with one account left: never from the API, only a database changed by hand
  { ...UNUSED, id: 103, name: "Gemini USD", kind: "exchange", currency: "USD", exchange_id: 3, exchange: "Gemini",
    sends_1099da: true },
];

const Section: React.FC = () => <LedgerAccounts {...useSettingsAccounts()} />;
/** As the app mounts it: StrictMode runs each effect twice in development. */
const Settings: React.FC = () => <React.StrictMode><Section /></React.StrictMode>;

beforeEach(() => {
  forgetAccounts();
  vi.spyOn(api, "get").mockImplementation(async (url: string) => ({ data: url === "/accounts/" ? BOOK : [] }));
  vi.spyOn(window, "confirm");
  vi.spyOn(api, "delete").mockResolvedValue({ status: 204 });
});

/** The row's Delete, its details open, and the dialog it opens. */
async function askToDelete(name: string) {
  const user = userEvent.setup();
  render(<Settings />);
  await user.click(await screen.findByRole("button", { name: new RegExp(`^${name}\\b`) }));
  const remove = within(screen.getByRole("region", { name })).getByRole("button", { name: "Delete" });
  fireEvent.click(remove); // as in Safari and the Mac app: a click that focuses no button
  return { user, remove, dialog: screen.getByRole("dialog", { name: `Delete ${name}?` }) };
}

it("asks in its own dialog, naming the account and the rule, never the browser's box", async () => {
  const { dialog } = await askToDelete("Coldcard");
  expect(dialog.textContent).toContain("This deletes the wallet Coldcard.");
  expect(dialog.textContent).toContain("Only an account with no transactions can be deleted, and it has none.");
  expect(window.confirm).not.toHaveBeenCalled();
  expect(api.delete).not.toHaveBeenCalled();
  // Cancel first, so Enter straight away deletes nothing
  expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Cancel" }));
});

it("names an exchange's two accounts, which go with it", async () => {
  const { dialog } = await askToDelete("Kraken");
  expect(dialog.textContent).toContain("This deletes the exchange Kraken and both its accounts, Kraken USD and Kraken BTC.");
  expect(dialog.textContent).toContain("Only an account with no transactions can be deleted, and they have none.");
});

it("an exchange with one account left is named alone", async () => {
  const { dialog } = await askToDelete("Gemini");
  expect(dialog.textContent).toContain("This deletes the exchange Gemini. Only an account with no transactions can be deleted, and it has none.");
});

it("Cancel and Escape send nothing, and the keyboard goes back to Delete", async () => {
  const { user, remove, dialog } = await askToDelete("Coldcard");
  await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(remove);
  await user.keyboard("{Enter}");
  expect(screen.getByRole("dialog", { name: "Delete Coldcard?" })).toBeTruthy();
  await user.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).toBeNull();
  expect(document.activeElement).toBe(remove);
  expect(api.delete).not.toHaveBeenCalled();
});

it("its Delete sends one request, says so while it runs, then closes, the keyboard on the row", async () => {
  let answer = (): void => undefined;
  vi.mocked(api.delete).mockReturnValue(new Promise((resolve) => (answer = () => resolve({ status: 204 }))));
  const { user, dialog } = await askToDelete("Coldcard");
  const confirm = within(dialog).getByRole("button", { name: "Delete Coldcard" });
  await user.dblClick(confirm);
  expect(api.delete).toHaveBeenCalledTimes(1);
  expect(api.delete).toHaveBeenCalledWith("/accounts/100");
  expect(confirm.textContent).toBe("Deleting...");
  expect(confirm).toHaveProperty("disabled", true);
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveProperty("disabled", true);
  expect(document.activeElement).toBe(dialog);
  await user.keyboard("{Escape}");
  expect(screen.getByRole("dialog")).toBe(dialog);
  await act(async () => answer());
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: /^Coldcard\b/ })));
  expect(window.confirm).not.toHaveBeenCalled();
});
