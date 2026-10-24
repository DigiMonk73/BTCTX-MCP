// River's exchange and wallet (#355; 2.0 spec 5.11, 5.13, Q8): the file's
// choice, never a hidden default, and a row's type change keeping it.
import { describe, expect, it } from "vitest";
import { MANY, ONE_OF_EACH } from "../test/books";
import {
  FIRST_RIVER_ACCOUNTS, chosenRiverAccounts, riverAccountNames, riverChoices, toEditableRow, typeChange,
} from "./riverImport";

const hide = (book: AccountBook, ids: number[]) => book.map((a) => (ids.includes(a.id) ? { ...a, hidden: true } : a));

describe("the file's exchange and wallet", () => {
  it("with one of each, are today's, chosen already, and nothing is asked", () => {
    const choices = riverChoices(ONE_OF_EACH);
    expect(choices.exchanges).toEqual([{ id: 4, name: "Exchange" }]);
    expect(choices.wallets).toEqual([{ id: 2, name: "Wallet" }]);
    expect(choices.defaults).toEqual({ exchange: 4, wallet: 2 });
    expect([choices.askExchange, choices.askWallet]).toEqual([false, false]);
  });

  it("with more than one, are asked, the first of each chosen (Q8), each exchange by its name", () => {
    const choices = riverChoices(MANY);
    // Closed and Old phone are hidden
    expect(choices.exchanges).toEqual([{ id: 4, name: "River" }, { id: 103, name: "Kraken" }]);
    expect(choices.wallets).toEqual([{ id: 2, name: "Sparrow" }, { id: 100, name: "Coldcard" }]);
    expect(choices.defaults).toEqual({ exchange: 4, wallet: 2 });
    expect([choices.askExchange, choices.askWallet]).toEqual([true, true]);
    // Only the kind with a choice is asked
    expect(riverChoices(hide(MANY, [100])).askWallet).toBe(false);
  });

  it("never default to a hidden one: the first shown is, and a hidden one isn't offered", () => {
    const choices = riverChoices(hide(MANY, [2, 3, 4]));
    expect(choices.defaults).toEqual({ exchange: 103, wallet: 100 });
    expect(choices.exchanges.map((e) => e.id)).toEqual([103]);
    expect([choices.askExchange, choices.askWallet]).toEqual([false, false]);
  });

  it("with every one of a kind hidden, ask with none chosen, among the hidden ones", () => {
    const choices = riverChoices(hide(MANY, [2, 100]));
    expect(choices.defaults).toEqual({ exchange: 4, wallet: undefined });
    expect(choices.wallets.map((w) => w.id)).toEqual([2, 100, 104]);
    expect(choices.askWallet).toBe(true);
  });

  it("are named in the rows as the import reads them: the exchange's BTC account, the wallet", () => {
    expect(riverAccountNames(MANY, { exchange: 103, wallet: 100 })).toEqual({
      exchange: "Kraken BTC", wallet: "Coldcard",
    });
    expect(riverAccountNames(ONE_OF_EACH, { exchange: 4, wallet: 2 })).toEqual(FIRST_RIVER_ACCOUNTS);
    expect(riverAccountNames(undefined, {})).toEqual(FIRST_RIVER_ACCOUNTS);
  });
});

describe("a row's type change keeps the file's exchange and wallet", () => {
  const proposal = (over: Partial<RiverProposal>): RiverProposal => ({
    row_number: 2, date: "2026-01-19T09:40:00Z", type: "Transfer", amount: "0.05", from_account: "Kraken BTC",
    to_account: "Coldcard", status: "new", type_choices: ["Transfer", "Withdrawal"], funding_choices: [],
    ...over,
  } as RiverProposal);
  const accounts = { exchange: "Kraken BTC", wallet: "Coldcard" };

  it("for a send from the exchange", () => {
    const sent = toEditableRow(proposal({}), accounts);
    expect(typeChange(sent, "Withdrawal")).toEqual({ type: "Withdrawal", fromAccount: "Kraken BTC", toAccount: "External" });
    const out = { ...sent, ...typeChange(sent, "Withdrawal") };
    expect(typeChange(out, "Transfer")).toEqual({ type: "Transfer", fromAccount: "Kraken BTC", toAccount: "Coldcard" });
  });

  it("for a receive into the exchange", () => {
    const received = toEditableRow(proposal({ from_account: "Coldcard", to_account: "Kraken BTC" }), accounts);
    expect(typeChange(received, "Deposit")).toEqual({ type: "Deposit", fromAccount: "External", toAccount: "Kraken BTC" });
    expect(typeChange(received, "Transfer")).toEqual({ type: "Transfer", fromAccount: "Coldcard", toAccount: "Kraken BTC" });
  });
});

describe("the pick", () => {
  it("is the owner's while it's offered, else the first shown one; nothing before the book is read", () => {
    const choices = riverChoices(MANY);
    expect(chosenRiverAccounts(choices, {})).toEqual({ exchange: 4, wallet: 2 });
    expect(chosenRiverAccounts(choices, { exchange: 103 })).toEqual({ exchange: 103, wallet: 2 });
    // Kraken hidden since it was picked: back to the first shown
    expect(chosenRiverAccounts(riverChoices(hide(MANY, [102, 103])), { exchange: 103 }))
      .toEqual({ exchange: 4, wallet: 2 });
    expect(chosenRiverAccounts(undefined, { exchange: 103 })).toEqual({});
  });
});
