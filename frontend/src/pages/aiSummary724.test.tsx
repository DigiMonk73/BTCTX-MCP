// @vitest-environment jsdom
// Settings' closed Connect an AI Assistant section sums up the key as its
// edition has it (#724): the Mac app makes its own key, which the open
// section calls "a key the app keeps in a private file"; Docker and StartOS
// have the owner create one. Until the edition is known, the summary names
// no key at all.
import "../test/setup";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import { ONE_OF_EACH } from "../test/books";
import Settings from "./Settings";

const REVIEW = { total: 0, reminders: 0, checks: [], recalc_error: null, timezone: "UTC" };
const MAC = { mode: "mac", on: true, has_key: true, key_file: "~/Library/Application Support/BitcoinTX/mcp.json" };
const SERVER = { mode: "server", on: false, has_key: false, key_file: null };

/** Settings, every section closed, with GET /settings/ai-access answered as `access` does. */
async function mount(access: () => Promise<unknown>) {
  window.localStorage.clear();
  const get = vi.spyOn(api, "get").mockImplementation(async (url: string) => {
    if (url === "/settings/ai-access") return access();
    if (url === "/health") return { data: { version: "2.0.0-alpha.2" } };
    if (url === "/review") return { data: REVIEW };
    if (url === "/accounts/") return { data: ONE_OF_EACH };
    if (url === "/calculations/accounts/balances") return { data: [] };
    throw new Error(`not in this test: ${url}`);
  });
  render(<MemoryRouter initialEntries={["/settings"]}><ToastProvider><Settings /></ToastProvider></MemoryRouter>);
  await waitFor(() => expect(get.mock.calls.some(([url]) => url === "/settings/ai-access")).toBe(true));
}

const summary = () => {
  const toggle = screen.getByRole("button", { name: "Connect an AI Assistant" });
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  return document.getElementById(toggle.getAttribute("aria-describedby") ?? "")?.textContent;
};

describe("Connect an AI Assistant's summary", () => {
  it("on the Mac app: a key BitcoinTX keeps, never one you create", async () => {
    await mount(async () => ({ data: MAC }));
    await waitFor(() => expect(summary()).toBe(
      "An AI app that reads your ledger and enters transactions, with a key BitcoinTX keeps for it",
    ));
  });

  it("on Docker and StartOS: a key you create", async () => {
    await mount(async () => ({ data: SERVER }));
    await waitFor(() => expect(summary()).toBe(
      "An AI app that reads your ledger and enters transactions, with a key you create",
    ));
  });

  it("while the edition isn't known, no key at all", async () => {
    await mount(async () => { throw new Error("offline"); });
    await waitFor(() => expect(summary()).toBe("An AI app that reads your ledger and enters transactions"));
  });
});
