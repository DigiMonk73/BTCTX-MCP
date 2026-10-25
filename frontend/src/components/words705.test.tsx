// @vitest-environment jsdom
// Four of the form's and the import's words, read at the moment of saving
// (#705): a wallet sent to itself moves no coins, an exchange's file isn't
// always River's, a bank pays for a one-off buy as well as a recurring one,
// and coins moved between your own accounts are a Transfer, never a Deposit.
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MANY, ONE_OF_EACH } from "../test/books";
import { offered, renderForm } from "../test/renderForm";
import { riverChoices } from "../utils/riverImport";
import RiverAccountPickers from "./riverImport/RiverAccountPickers";

const TRANSFER_NOT_DEPOSIT =
  "Coins moved here from another wallet or exchange you track in BitcoinTX are a Transfer, not a Deposit: " +
  "a deposit would count them in both accounts.";

describe("a wallet sent to itself", () => {
  it("is a consolidation only, and a move to another wallet is pointed at that wallet", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Transfer");
    await form.choose("From Account", "Coldcard");
    expect(offered("To Account")).toContain("Wallets: Coldcard: consolidate within the same wallet");
    await form.choose("To Account", "Coldcard: consolidate within the same wallet");
    expect(screen.getByText(
      "Moving coins to another of your wallets? Choose that wallet as To Account, after adding it in " +
      "Settings → Wallets, exchanges and banks if it isn't listed.",
    )).toBeTruthy();
  });
});

describe("an exchange's file", () => {
  it("names no exchange in its wallet's hint: the file may be any exchange's", () => {
    const choices = riverChoices(MANY);
    render(<RiverAccountPickers choices={choices} chosen={choices.defaults} disabled={false} outOfDate={false}
      onChange={() => {}} />);
    expect(document.getElementById("river-wallet-hint")?.textContent)
      .toBe("This file's sends to your wallet go into it, and its receives come from it.");
  });
});

describe("a Buy's Paid from", () => {
  it("names each bank as it's named, a one-off buy's as well as a recurring one's", async () => {
    const form = await renderForm({ book: MANY });
    await form.pickType("Buy");
    await form.choose("Exchange", "Kraken");
    expect(offered("Paid from")).toEqual(["Exchanges: Kraken USD", "Banks: Checking", "Banks: Savings"]);
  });
});

describe("a bitcoin Deposit", () => {
  it("says a move from another of your accounts is a Transfer, while its source is your own coins", async () => {
    const form = await renderForm({ book: ONE_OF_EACH });
    await form.pickType("Deposit");
    await form.choose("Account", "Wallet");
    expect(screen.getByText(TRANSFER_NOT_DEPOSIT)).toBeTruthy(); // N/A, the first choice
    await form.choose("Source", "MyBTC");
    expect(screen.getByText(TRANSFER_NOT_DEPOSIT)).toBeTruthy();
    await form.choose("Source", "Income");
    expect(screen.queryByText(TRANSFER_NOT_DEPOSIT)).toBeNull();
  });

  it("says nothing of it for dollars", async () => {
    const form = await renderForm({ book: ONE_OF_EACH });
    await form.pickType("Deposit");
    await form.choose("Account", "Bank");
    expect(screen.queryByText(TRANSFER_NOT_DEPOSIT)).toBeNull();
  });
});
