// @vitest-environment jsdom
// B7b-2's proving test: Hide, Show and Delete on Settings' accounts (spec 5.9).
// Each write is one request, then the book is asked for again; a refusal shows
// the server's sentence unchanged. Delete is offered only on an account no
// transaction names, and the server alone refuses 1 to 4 (no id in the page).
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { TWO_BALANCES, TWO_OF_EACH } from "../../test/accountBooks";
import { renderSettings, type RenderedSettings } from "../../test/renderSettings";

const IN_USE = "This account has transactions, so it can't be deleted. Hide it instead: its history stays.";
const FIRST_ONES = "Your first bank, wallet and exchange can't be deleted. Hide one you don't use.";

const row = (name: string) => screen.getByRole("listitem", { name });
const button = (name: string, label: string) => within(row(name)).getByRole("button", { name: label });
const noButton = (name: string, label: string) => within(row(name)).queryByRole("button", { name: label });

/** The requests after the first two reads, as "<method> <url>". */
const writesAndReads = (s: RenderedSettings) => s.requests.slice(2).map((r) => `${r.method} ${r.url}`);

async function click(s: RenderedSettings, name: string, label: string): Promise<void> {
  await s.user.click(button(name, label));
  await s.settle();
}

afterEach(() => vi.restoreAllMocks());

describe("Hide and Show", () => {
  it("Hide on Cold Storage sends hidden: true, asks for the book again and says so", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await click(s, "Cold Storage", "Hide");
    expect(s.requests[2]).toEqual({ method: "put", url: "/accounts/101", body: { hidden: true } });
    expect(writesAndReads(s)).toEqual(["put /accounts/101", "get /accounts/"]);
    expect(row("Cold Storage")).toHaveTextContent("Hidden");
    expect(button("Cold Storage", "Show")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Hidden.");
  });

  it("Show on Old Wallet sends hidden: false", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    expect(noButton("Old Wallet", "Hide")).toBeNull();
    await click(s, "Old Wallet", "Show");
    expect(s.requests[2]).toEqual({ method: "put", url: "/accounts/104", body: { hidden: false } });
    expect(row("Old Wallet")).not.toHaveTextContent("Hidden");
    expect(screen.getByRole("status")).toHaveTextContent("Shown.");
  });

  it("Hide on an exchange's account shows both halves hidden, as the server hides both", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await click(s, "Kraken BTC", "Hide");
    expect(s.requests[2]).toEqual({ method: "put", url: "/accounts/103", body: { hidden: true } });
    expect(row("Kraken USD")).toHaveTextContent("Hidden");
    expect(row("Kraken BTC")).toHaveTextContent("Hidden");
  });
});

describe("Delete", () => {
  it("is offered only on an account no transaction names", async () => {
    await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    for (const name of ["Bank", "Wallet", "Cold Storage", "Exchange BTC", "Kraken BTC"]) {
      expect(noButton(name, "Delete")).toBeNull();
    }
    expect(button("Credit Union", "Delete")).toBeInTheDocument();
    expect(button("Kraken USD", "Delete")).toBeInTheDocument();
  });

  it("asks first, then sends DELETE and lists the book again without it", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await click(s, "Credit Union", "Delete");
    expect(confirm).toHaveBeenCalledWith("Delete Credit Union?");
    expect(writesAndReads(s)).toEqual(["delete /accounts/100", "get /accounts/"]);
    expect(screen.queryByRole("listitem", { name: "Credit Union" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Deleted.");
  });

  it("sends nothing when the owner cancels", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await click(s, "Credit Union", "Delete");
    expect(writesAndReads(s)).toEqual([]);
    expect(row("Credit Union")).toBeInTheDocument();
  });

  it("shows the server's 400 for an unused first account word for word", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const unusedBank = TWO_OF_EACH.map((a) => (a.id === 1 ? { ...a, in_use: false } : a));
    const s = await renderSettings({
      book: unusedBank, balances: TWO_BALANCES,
      refuse: { "delete /accounts/1": { status: 400, body: { detail: FIRST_ONES } } },
    });
    await click(s, "Bank", "Delete");
    expect(writesAndReads(s)).toEqual(["delete /accounts/1"]);
    expect(screen.getByRole("status")).toHaveTextContent(FIRST_ONES);
    expect(row("Bank")).toBeInTheDocument();
  });

  it("shows the server's 409 word for word (a transaction saved meanwhile)", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const s = await renderSettings({
      book: TWO_OF_EACH, balances: TWO_BALANCES,
      refuse: { "delete /accounts/102": { status: 409, body: { detail: IN_USE } } },
    });
    await click(s, "Kraken USD", "Delete");
    expect(screen.getByRole("status")).toHaveTextContent(IN_USE);
  });

  it("deleting an exchange's account takes both halves off the list, as the server deletes both", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const unusedKraken = TWO_OF_EACH.map((a) => (a.exchange_id === 2 ? { ...a, in_use: false } : a));
    const s = await renderSettings({ book: unusedKraken, balances: TWO_BALANCES });
    await click(s, "Kraken USD", "Delete");
    expect(screen.queryByRole("listitem", { name: "Kraken USD" })).toBeNull();
    expect(screen.queryByRole("listitem", { name: "Kraken BTC" })).toBeNull();
  });
});

describe("while a write runs", () => {
  it("the section's buttons wait (the page's loading state)", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    let release = () => {};
    const { default: api } = await import("../../api");
    vi.spyOn(api, "put").mockImplementation(() => new Promise((resolve) => {
      release = () => resolve({ data: [], status: 200, statusText: "OK", headers: {}, config: {} as never });
    }));
    await s.user.click(button("Cold Storage", "Hide"));
    expect(button("Wallet", "Hide")).toBeDisabled();
    release();
    await s.settle();
  });
});
