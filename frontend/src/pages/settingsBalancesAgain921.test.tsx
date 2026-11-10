// @vitest-environment jsdom
// Settings' sections stay mounted while closed, and Delete All, the imports
// and a restore change the balances meanwhile: the accounts section reads
// them again each time it opens, as it does the book (#720), so its rows
// never keep the balances from before (#921).
import "../test/setup";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import { ONE_OF_EACH } from "../test/books";
import Settings from "./Settings";

const REVIEW = { total: 0, reminders: 0, checks: [], recalc_error: null, timezone: "UTC" };

/** The balances as GET /calculations/accounts/balances lists them: the wallet's and the bank's. */
function balances(wallet: string, bank: string): AccountBalance[] {
  const one = (account_id: number, name: string, currency: string, balance: string, kind: AccountKind) =>
    ({ account_id, name, currency, balance, kind, exchange_id: null, exchange: null }) as AccountBalance;
  return [one(2, "Wallet", "BTC", wallet, "wallet"), one(1, "Bank", "USD", bank, "bank")];
}

it("reads the balances again as the accounts section opens: Delete All's zeros show at once", async () => {
  window.localStorage.clear(); // every section closed, as a new browser has them
  let server = balances("0.3997", "45000.00");
  const get = vi.spyOn(api, "get").mockImplementation(async (url: string) => {
    if (url === "/accounts/") return { data: ONE_OF_EACH };
    if (url === "/review") return { data: REVIEW };
    if (url === "/calculations/accounts/balances") return { data: server };
    throw new Error(`not in this test: ${url}`);
  });
  render(<MemoryRouter initialEntries={["/settings"]}><ToastProvider><Settings /></ToastProvider></MemoryRouter>);
  const user = userEvent.setup();
  const asked = () => get.mock.calls.filter(([url]) => url === "/calculations/accounts/balances").length;
  // Closed, it asks for none: the book is read, the balances wait for the section
  await waitFor(() => expect(get.mock.calls.some(([url]) => url === "/accounts/")).toBe(true));
  expect(asked()).toBe(0);

  const section = screen.getByRole("button", { name: "Wallets, exchanges and banks" });
  await user.click(section);
  expect(await screen.findByText("0.39970000 BTC")).toBeTruthy();
  expect(screen.getByText("$45,000.00")).toBeTruthy();

  // Data Management opens (one at a time) and its Delete All deletes every transaction
  await user.click(screen.getByRole("button", { name: "Data Management" }));
  server = balances("0", "0");
  const before = asked();
  await user.click(section);
  await waitFor(() => expect(screen.getByText("0.00000000 BTC")).toBeTruthy());
  expect(screen.getByText("$0.00")).toBeTruthy();
  expect(screen.queryByText("0.39970000 BTC")).toBeNull();
  expect(asked()).toBe(before + 1); // one read as it opens again
});
