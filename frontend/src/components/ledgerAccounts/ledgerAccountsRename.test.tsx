// @vitest-environment jsdom
// B8-5n's proving test: Settings' Rename (spec 5.9, #356 item 4; Rick,
// 2026-10-20: the field is "Nickname", and the list shows it). One PUT
// {name}, then the book again; an exchange's account renames its exchange and
// both its accounts (the server does both, B8-5r); a refusal is shown as the
// server says it, and the field stays open with the name typed.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { TWO_BALANCES, TWO_OF_EACH } from "../../test/accountBooks";
import { renderSettings, type RenderedSettings } from "../../test/renderSettings";

const TAKEN = "An account named 'Wallet' already exists.";

const row = (name: string) => screen.getByRole("listitem", { name });

async function rename(s: RenderedSettings, from: string, to: string): Promise<void> {
  await s.user.click(within(row(from)).getByRole("button", { name: "Rename" }));
  const form = screen.getByRole("form", { name: `Rename ${from}` });
  const field = within(form).getByLabelText("Nickname");
  await s.user.clear(field);
  await s.user.type(field, to);
  await s.user.click(within(form).getByRole("button", { name: "Save" }));
  await s.settle();
}

/** The requests after the first two reads, as "<method> <url>". */
const writesAndReads = (s: RenderedSettings) => s.requests.slice(2).map((r) => `${r.method} ${r.url}`);

afterEach(() => vi.restoreAllMocks());

describe("Rename", () => {
  it("offers Rename on every account listed, the fee accounts never listed", async () => {
    await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    for (const item of screen.getAllByRole("listitem")) {
      expect(within(item).getByRole("button", { name: "Rename" })).toBeInTheDocument();
    }
    expect(screen.getAllByRole("listitem")).toHaveLength(9);
  });

  it("opens the Nickname field on the nickname the account has", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await s.user.click(within(row("Cold Storage")).getByRole("button", { name: "Rename" }));
    const form = screen.getByRole("form", { name: "Rename Cold Storage" });
    expect(within(form).getByLabelText("Nickname")).toHaveValue("Cold Storage");
  });

  it("renames Cold Storage to Ledger Nano: one PUT {name}, then the book again", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await rename(s, "Cold Storage", "Ledger Nano");
    expect(s.requests[2]).toEqual({ method: "put", url: "/accounts/101", body: { name: "Ledger Nano" } });
    expect(writesAndReads(s)).toEqual(["put /accounts/101", "get /accounts/"]);
    expect(row("Ledger Nano")).toHaveTextContent("Wallet · 0.25000000 BTC");
    expect(screen.queryByRole("listitem", { name: "Cold Storage" })).toBeNull();
    expect(screen.queryByRole("form")).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Renamed.");
  });

  it("renames an exchange from either account: its field holds the exchange's nickname", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await s.user.click(within(row("Kraken BTC")).getByRole("button", { name: "Rename" }));
    const form = screen.getByRole("form", { name: "Rename Kraken BTC" });
    expect(within(form).getByLabelText("Nickname")).toHaveValue("Kraken");
    await s.user.click(within(form).getByRole("button", { name: "Cancel" }));
    await rename(s, "Kraken USD", "Kraken Pro");
    expect(s.requests[2]).toEqual({ method: "put", url: "/accounts/102", body: { name: "Kraken Pro" } });
    expect(row("Kraken Pro USD")).toBeInTheDocument();
    expect(row("Kraken Pro BTC")).toBeInTheDocument();
  });

  it("says what an exchange's two accounts will be called, as Add does", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await s.user.click(within(row("Kraken BTC")).getByRole("button", { name: "Rename" }));
    const form = screen.getByRole("form", { name: "Rename Kraken BTC" });
    await s.user.clear(within(form).getByLabelText("Nickname"));
    await s.user.type(within(form).getByLabelText("Nickname"), "Kraken Pro");
    expect(form).toHaveTextContent(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'Kraken Pro USD' and 'Kraken Pro BTC'.",
    );
    await s.user.click(within(row("Cold Storage")).getByRole("button", { name: "Rename" }));
    expect(screen.getByRole("form", { name: "Rename Cold Storage" })).not.toHaveTextContent("two accounts");
  });

  it("renames Wallet to Wallet 2 and back: both PUTs go (5.1: 1 to 4 renamed, and renamed back)", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await rename(s, "Wallet", "Wallet 2");
    await rename(s, "Wallet 2", "Wallet");
    expect(s.requests.filter((r) => r.method === "put")).toEqual([
      { method: "put", url: "/accounts/2", body: { name: "Wallet 2" } },
      { method: "put", url: "/accounts/2", body: { name: "Wallet" } },
    ]);
    expect(row("Wallet")).toBeInTheDocument();
  });

  it("shows the server's refusal unchanged, and keeps the field open with the name typed", async () => {
    const s = await renderSettings({
      book: TWO_OF_EACH, balances: TWO_BALANCES, refuse: { "put /accounts/101": { status: 400, body: { detail: TAKEN } } },
    });
    await rename(s, "Cold Storage", "Wallet");
    expect(screen.getByRole("status")).toHaveTextContent(TAKEN);
    expect(writesAndReads(s)).toEqual(["put /accounts/101"]);
    const form = screen.getByRole("form", { name: "Rename Cold Storage" });
    expect(within(form).getByLabelText("Nickname")).toHaveValue("Wallet");
  });

  it("sends the name as typed: the server trims it", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await rename(s, "Credit Union", "  Savings ");
    expect(s.requests[2].body).toEqual({ name: "  Savings " });
  });

  it("Cancel closes the field and sends nothing", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await s.user.click(within(row("Bank")).getByRole("button", { name: "Rename" }));
    await s.user.click(within(screen.getByRole("form", { name: "Rename Bank" })).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("form")).toBeNull();
    expect(writesAndReads(s)).toEqual([]);
  });
});
