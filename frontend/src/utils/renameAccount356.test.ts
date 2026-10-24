import { describe, expect, it } from "vitest";
import { MANY, ONE_OF_EACH } from "../test/books";
import { accountGroups, renameFilesNote, renameHelp, renameReady, type AccountRow } from "./ledgerAccounts";

/** A book's row by its name ("Wallet", "River"). */
function rowOf(book: AccountBook, name: string): AccountRow {
  const rows = accountGroups(book).flatMap((g) => [...g.shown, ...g.hidden]);
  return rows.find((r) => r.name === name) as AccountRow;
}

describe("Settings' Rename (#356, 2.0 spec 5.9)", () => {
  it("sends a name only once it's another one, as the server would keep it", () => {
    const wallet = rowOf(ONE_OF_EACH, "Wallet");
    expect(renameReady(wallet, "Coldcard")).toBe(true);
    expect(renameReady(wallet, "wallet")).toBe(true); // its case is a change too
    expect(renameReady(wallet, "Wallet")).toBe(false);
    expect(renameReady(wallet, "  Wallet ")).toBe(false); // the ends' spaces go
    expect(renameReady(wallet, "")).toBe(false);
    expect(renameReady(wallet, "  ")).toBe(false);
  });

  it("an exchange's row renames the exchange: its name is the exchange's", () => {
    const river = rowOf(MANY, "River");
    expect(renameReady(river, "River")).toBe(false);
    expect(renameReady(river, "River Financial")).toBe(true);
  });

  it("says what an exchange's two accounts become, as Add says it", () => {
    expect(renameHelp(rowOf(MANY, "River"), "  Coinbase   Pro ")).toBe(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'Coinbase Pro USD' and 'Coinbase Pro BTC'.");
    expect(renameHelp(rowOf(MANY, "Coldcard"), "Jade")).toBeNull();
    expect(renameHelp(rowOf(MANY, "Checking"), "Savings 2")).toBeNull();
  });

  const FILES = "A CSV file names each account as it was named when the file was saved, and an import matches " +
    "those names to your accounts as they're named then: a file saved before this rename names this account by " +
    "its old name.";

  it("says how files name a renamed account (5.11)", () => {
    expect(renameFilesNote(rowOf(MANY, "Coldcard"))).toBe(FILES);
    expect(renameFilesNote(rowOf(MANY, "Kraken"))).toBe(FILES);
  });

  it("the first bank, wallet and exchange keep their old names' meaning in files (5.1's reserved names)", () => {
    expect(renameFilesNote(rowOf(MANY, "Checking"))).toBe(`${FILES} In a file, 'Bank' still means this account.`);
    expect(renameFilesNote(rowOf(MANY, "Sparrow"))).toBe(`${FILES} In a file, 'Wallet' still means this account.`);
    expect(renameFilesNote(rowOf(MANY, "River"))).toBe(
      `${FILES} In a file, 'Exchange USD' and 'Exchange BTC' still mean this exchange's accounts.`);
  });
});
