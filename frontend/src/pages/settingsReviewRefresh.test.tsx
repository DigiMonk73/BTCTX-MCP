// @vitest-environment jsdom
// Settings asks Ledger Review again once another section saved what it reads
// (#355, #645): the tax timezone (its times and tax years), Recalculate
// Ledger (the figures it would change), an exchange's 1099-DA switch (its
// "sale may differ" check, exchangeSwitch355.test.tsx). Ledger Review's
// section stays mounted, and otherwise loads only when the page opens.
import "../test/setup";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import { ONE_OF_EACH } from "../test/books";
import Settings from "./Settings";

const REVIEW = { total: 0, reminders: 0, checks: [], recalc_error: null, timezone: "UTC" };

/** What the page asks of the server: the review and what Settings needs; anything else isn't there. */
function answer(url: string) {
  if (url === "/review") return { data: REVIEW };
  if (url === "/accounts/") return { data: ONE_OF_EACH };
  if (url === "/calculations/accounts/balances") return { data: [] };
  if (url === "/settings/tax-timezone") return { data: { timezone: "UTC", source: "setting" } };
  throw new Error(`not in this test: ${url}`);
}

async function mount() {
  window.localStorage.clear(); // every section closed, as a new browser has them
  const get = vi.spyOn(api, "get").mockImplementation(async (url: string) => answer(url));
  vi.spyOn(api, "put").mockResolvedValue({ data: { timezone: "Asia/Tokyo", source: "setting" } });
  vi.spyOn(api, "post").mockResolvedValue({ data: { detail: "Recalculated 0 transaction(s)." } });
  render(<MemoryRouter initialEntries={["/settings"]}><ToastProvider><Settings /></ToastProvider></MemoryRouter>);
  const reviews = () => get.mock.calls.filter(([url]) => url === "/review").length;
  await waitFor(() => expect(reviews()).toBe(1));
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Account" }));
  return { user, reviews };
}

describe("Ledger Review, after another section saved", () => {
  it("is asked again once a new tax timezone is saved", async () => {
    const view = await mount();
    await screen.findByText("UTC", { selector: "strong" });
    await view.user.selectOptions(screen.getByLabelText("Tax timezone"), "Asia/Tokyo");
    await view.user.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(view.reviews()).toBe(2));
  });

  it("is asked again once Recalculate Ledger has run", async () => {
    const view = await mount();
    await view.user.click(screen.getByRole("button", { name: "Recalculate" }));
    await waitFor(() => expect(view.reviews()).toBe(2));
  });
});
