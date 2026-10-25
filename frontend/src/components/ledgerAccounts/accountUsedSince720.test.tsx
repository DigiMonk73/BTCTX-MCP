// @vitest-environment jsdom
// An account used since the page read the book (#720): a deposit saved on
// the Transactions page, or by the AI connector, while the page stayed open.
// Settings reads the book afresh as it opens, and again after a refused
// delete, so its row never says "It has no transactions." with Delete
// offered for an account that has some.
import "../../test/setup";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { beforeEach, expect, it, vi } from "vitest";
import api from "../../api";
import { ONE_OF_EACH } from "../../test/books";
import { forgetAccounts, useAccounts } from "../../utils/useAccounts";
import { useSettingsAccounts } from "../../utils/useSettingsAccounts";
import LedgerAccounts from "../LedgerAccounts";

const COLDCARD: LedgerAccount = {
  id: 100, name: "Coldcard", kind: "wallet", currency: "BTC", exchange_id: null, exchange: null, sends_1099da: null,
  hidden: false, in_use: false,
};
const UNUSED: AccountBook = [...ONE_OF_EACH, COLDCARD];
const USED: AccountBook = [...ONE_OF_EACH, { ...COLDCARD, in_use: true }];
const IN_USE = "This account has transactions, so it can't be deleted. Hide it instead: its history stays.";

function refused(status: number, detail: string): AxiosError {
  const response = { data: { detail }, status, statusText: "", headers: {}, config: {} } as AxiosResponse;
  return new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_REQUEST", undefined, undefined, response);
}

/** Settings' section, as the page mounts it. */
const Settings: React.FC = () => <LedgerAccounts {...useSettingsAccounts()} />;

/** A screen that read the book earlier on the page (the transaction form). */
const Form: React.FC = () => <p>{useAccounts().book ? "form ready" : "form loading"}</p>;

// The book as the server has it now; the balances are none
let server: AccountBook;
beforeEach(() => {
  forgetAccounts();
  vi.spyOn(api, "get").mockImplementation(async (url: string) => ({ data: url === "/accounts/" ? server : [] }));
});

async function openColdcard() {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /^Coldcard\b/ }));
  return { user, details: screen.getByRole("region", { name: "Coldcard" }) };
}

it("reads the book afresh as Settings opens: an account used since offers no Delete", async () => {
  server = UNUSED;
  const form = render(<Form />);
  await screen.findByText("form ready");
  form.unmount();
  server = USED; // a deposit into Coldcard saved on the Transactions page
  render(<Settings />);
  const { details } = await openColdcard();
  await waitFor(() => expect(within(details).getByText(IN_USE)).toBeTruthy());
  expect(within(details).queryByRole("button", { name: "Delete" })).toBeNull();
  expect(within(details).queryByText("It has no transactions.")).toBeNull();
});

it("reads it again after a refused delete: the server's words, and the row as the server has it", async () => {
  server = UNUSED;
  render(<Settings />);
  const { user, details } = await openColdcard();
  const remove = await within(details).findByRole("button", { name: "Delete" });
  server = USED; // used by the AI connector while Settings stayed open
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(api, "delete").mockRejectedValue(refused(409, IN_USE));
  const balances = () => vi.mocked(api.get).mock.calls.filter(([url]) => url !== "/accounts/").length;
  const balancesBefore = balances();
  await user.click(remove);
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", IN_USE);
  await waitFor(() => expect(within(details).queryByRole("button", { name: "Delete" })).toBeNull());
  expect(within(details).getByText(IN_USE)).toBeTruthy();
  expect(balances()).toBe(balancesBefore + 1);
  // The keyboard back on the row, as after every change here: its Delete button is gone
  await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: /^Coldcard\b/ })));
});
