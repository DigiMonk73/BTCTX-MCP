// @vitest-environment jsdom
// B7b-3's proving test: "Add a wallet", "Add an exchange" and "Add a bank" in
// Settings (spec 5.9), with the help texts word for word (5.1, 5.9) and Q5's
// note for a second wallet or exchange (5.8). The name goes as typed: the server
// trims it and refuses what it must, and its words are shown unchanged.
import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import { ONE_OF_EACH, TWO_BALANCES, TWO_OF_EACH } from "../../test/accountBooks";
import { renderSettings, type RenderedSettings } from "../../test/renderSettings";
import { addHelp, pooledNote } from "../../utils/ledgerAccounts";

const WALLET_HELP =
  "A wallet is one set of keys: every address it makes is part of it. A backup of the same keys (a seed phrase, " +
  "or another device with the same keys) isn't a second wallet. If you use multiple wallets, add each one: since " +
  "2025 the IRS figures cost basis wallet by wallet.";
const WALLET_NOTE =
  "Years before you add this wallet were figured with your wallets together, as BitcoinTX 1.x did. Move coins " +
  "into it with a Transfer dated when they really moved: BitcoinTX moves the oldest coins first. A Transfer dated " +
  "in an earlier year can change that year's figures and later ones (BitcoinTX shows which years before it " +
  "saves), and BitcoinTX doesn't allocate your cost basis to each wallet as of January 1, 2025 (Rev. Proc. " +
  "2024-28). A tax professional can tell you whether an earlier return needs a change.";
const EXCHANGE_NOTE =
  "Years before you add this exchange were figured with your exchange accounts together, as BitcoinTX 1.x did. " +
  "Move coins into it with a Transfer dated when they really moved: BitcoinTX moves the oldest coins first. A " +
  "Transfer dated in an earlier year can change that year's figures and later ones (BitcoinTX shows which years " +
  "before it saves), and BitcoinTX doesn't allocate your cost basis to each exchange account as of January 1, " +
  "2025 (Rev. Proc. 2024-28). A tax professional can tell you whether an earlier return needs a change.";

/** A book with nothing of `kind` in use: Q5's note has nothing to warn about. */
const unused = (book: AccountBook, kind: AccountKind): AccountBook =>
  book.map((a) => (a.kind === kind ? { ...a, in_use: false } : a));

async function open(s: RenderedSettings, label: string): Promise<void> {
  await s.user.click(screen.getByRole("button", { name: label }));
}

async function type(s: RenderedSettings, name: string): Promise<void> {
  await s.user.type(screen.getByRole("textbox", { name: "Nickname" }), name);
}

async function add(s: RenderedSettings): Promise<void> {
  await s.user.click(screen.getByRole("button", { name: "Add" }));
  await s.settle();
}

afterEach(() => vi.restoreAllMocks());

describe("the texts (utils/ledgerAccounts.ts)", () => {
  it("a wallet's help is 5.1's, whatever its name", () => {
    expect(addHelp("wallet", "Cold Storage")).toBe(WALLET_HELP);
    expect(addHelp("wallet", "")).toBe(WALLET_HELP);
  });

  it("an exchange's help names its two accounts from the name typed", () => {
    expect(addHelp("exchange", "Kraken")).toBe(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'Kraken USD' and 'Kraken BTC'.");
    expect(addHelp("exchange", "  Kraken ")).toBe(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'Kraken USD' and 'Kraken BTC'.");
  });

  it("an exchange's help before a name is typed says 'name'", () => {
    expect(addHelp("exchange", " ")).toBe(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'name USD' and 'name BTC'.");
  });

  it("a bank has no help", () => {
    expect(addHelp("bank", "Credit Union")).toBeNull();
  });

  it("Q5's note: a second wallet or exchange while one of that kind is in use", () => {
    expect(pooledNote(TWO_OF_EACH, "wallet")).toBe(WALLET_NOTE);
    expect(pooledNote(TWO_OF_EACH, "exchange")).toBe(EXCHANGE_NOTE);
    expect(pooledNote(ONE_OF_EACH, "wallet")).toBe(WALLET_NOTE);
  });

  it("no note when none of that kind is in use, nor ever for a bank", () => {
    expect(pooledNote(unused(TWO_OF_EACH, "wallet"), "wallet")).toBeNull();
    expect(pooledNote(unused(TWO_OF_EACH, "exchange"), "exchange")).toBeNull();
    expect(pooledNote(TWO_OF_EACH, "bank")).toBeNull();
  });
});

describe("adding (components/ledgerAccounts/AddAccount.tsx)", () => {
  it("offers the three, and no field until one is opened", async () => {
    await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    for (const label of ["Add a wallet", "Add an exchange", "Add a bank"]) {
      expect(screen.getByRole("button", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("textbox", { name: "Nickname" })).toBeNull();
  });

  it("an exchange: its help follows the name, and Add sends kind and name", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await open(s, "Add an exchange");
    await type(s, "Bitstamp");
    expect(screen.getByText(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'Bitstamp USD' and 'Bitstamp BTC'.",
    )).toBeInTheDocument();
    expect(screen.getByText(EXCHANGE_NOTE)).toBeInTheDocument();
    await add(s);
    expect(s.requests.slice(2).map((r) => `${r.method} ${r.url}`)).toEqual(["post /accounts/", "get /accounts/"]);
    expect(s.requests[2].body).toEqual({ kind: "exchange", name: "Bitstamp" });
    expect(screen.getByRole("listitem", { name: "Bitstamp USD" })).toBeInTheDocument();
    expect(screen.getByRole("listitem", { name: "Bitstamp BTC" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Added.");
    expect(screen.queryByRole("textbox", { name: "Nickname" })).toBeNull(); // closed once added
  });

  it("a wallet with wallets in use: 5.1's help and Q5's wallet note", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await open(s, "Add a wallet");
    expect(screen.getByText(WALLET_HELP)).toBeInTheDocument();
    expect(screen.getByText(WALLET_NOTE)).toBeInTheDocument();
    await type(s, "Hardware");
    await add(s);
    expect(s.requests[2].body).toEqual({ kind: "wallet", name: "Hardware" });
  });

  it("a wallet with none in use: the help, no note", async () => {
    const s = await renderSettings({ book: unused(TWO_OF_EACH, "wallet"), balances: TWO_BALANCES });
    await open(s, "Add a wallet");
    expect(screen.getByText(WALLET_HELP)).toBeInTheDocument();
    expect(screen.queryByText(WALLET_NOTE)).toBeNull();
  });

  it("a bank: neither help nor note", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await open(s, "Add a bank");
    expect(screen.queryByText(WALLET_HELP)).toBeNull();
    expect(screen.queryByText(WALLET_NOTE)).toBeNull();
    expect(screen.queryByText(EXCHANGE_NOTE)).toBeNull();
    await type(s, "Savings");
    await add(s);
    expect(s.requests[2].body).toEqual({ kind: "bank", name: "Savings" });
  });

  it("the server's 400 is shown unchanged, and the field stays open with the name", async () => {
    const detail = "An account named 'Kraken' already exists.";
    const s = await renderSettings({
      book: TWO_OF_EACH, balances: TWO_BALANCES,
      refuse: { "post /accounts/": { status: 400, body: { detail } } },
    });
    await open(s, "Add an exchange");
    await type(s, "Kraken");
    await add(s);
    expect(screen.getByRole("status")).toHaveTextContent(detail);
    expect(screen.getByRole("textbox", { name: "Nickname" })).toHaveValue("Kraken");
  });

  it("a 37-character exchange name is sent as typed: the server refuses it, never the page", async () => {
    const name = "x".repeat(37);
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await open(s, "Add an exchange");
    await type(s, name);
    await add(s);
    expect(s.requests[2].body).toEqual({ kind: "exchange", name });
  });

  it("Cancel closes the field and sends nothing", async () => {
    const s = await renderSettings({ book: TWO_OF_EACH, balances: TWO_BALANCES });
    await open(s, "Add a wallet");
    await type(s, "Hardware");
    await s.user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("textbox", { name: "Nickname" })).toBeNull();
    expect(s.requests).toHaveLength(2);
  });
});
