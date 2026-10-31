// @vitest-environment jsdom
// Settings' sections stay mounted while closed, and two of them save
// transactions (Import from an exchange, Data Management's CSV import and
// Delete All): the accounts section reads the book again each time it opens
// (#720), so a row never says "It has no transactions." with Delete offered
// for an account one of them used.
import "../test/setup";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import { ONE_OF_EACH } from "../test/books";
import Settings from "./Settings";

const COLDCARD: LedgerAccount = {
  id: 100, name: "Coldcard", kind: "wallet", currency: "BTC", exchange_id: null, exchange: null, sends_1099da: null,
  hidden: false, in_use: false,
};
const IN_USE = "This account has transactions, so it can't be deleted. Hide it instead: its history stays.";
const REVIEW = { total: 0, reminders: 0, checks: [], recalc_error: null, timezone: "UTC" };

it("reads the book again as the accounts section opens: an account another section used offers no Delete", async () => {
  window.localStorage.clear(); // every section closed, as a new browser has them
  let server: AccountBook = [...ONE_OF_EACH, COLDCARD];
  const get = vi.spyOn(api, "get").mockImplementation(async (url: string) => {
    if (url === "/accounts/") return { data: server };
    if (url === "/review") return { data: REVIEW };
    if (url === "/calculations/accounts/balances") return { data: [] };
    throw new Error(`not in this test: ${url}`);
  });
  render(<MemoryRouter initialEntries={["/settings"]}><ToastProvider><Settings /></ToastProvider></MemoryRouter>);
  const user = userEvent.setup();
  const books = () => get.mock.calls.filter(([url]) => url === "/accounts/").length;
  await waitFor(() => expect(books()).toBe(1));

  await user.click(screen.getByRole("button", { name: "Wallets, exchanges and banks" }));
  await user.click(await screen.findByRole("button", { name: /^Coldcard\b/ }));
  const details = screen.getByRole("region", { name: "Coldcard" });
  expect(within(details).getByRole("button", { name: "Delete" })).toBeTruthy();

  // Another section opens (one at a time) and its import saves a deposit into Coldcard
  await user.click(screen.getByRole("button", { name: "Import from an exchange" }));
  server = [...ONE_OF_EACH, { ...COLDCARD, in_use: true }];
  const before = books();
  await user.click(screen.getByRole("button", { name: "Wallets, exchanges and banks" }));
  await waitFor(() => expect(within(details).getByText(IN_USE)).toBeTruthy());
  expect(within(details).queryByRole("button", { name: "Delete" })).toBeNull();
  expect(books()).toBe(before + 1); // one read as it opens again
});
