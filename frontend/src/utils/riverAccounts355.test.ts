// River's exchange and wallet (#355; 2.0 spec 5.11, 5.13, Q8): the file's
// choice, never a hidden default, and a row's type change keeping it.
import { describe, expect, it } from "vitest";
import { MANY, ONE_OF_EACH } from "../test/books";
import {
  FIRST_RIVER_ACCOUNTS, chosenRiverAccounts, pickNeeded, previewOutOfDate, riverAccountNames, riverChoices,
  toEditableRow,
  typeChange,
} from "./riverImport";

const hide = (book: AccountBook, ids: number[]) => book.map((a) => (ids.includes(a.id) ? { ...a, hidden: true } : a));

describe("the file's exchange and wallet", () => {
  it("with one of each, are today's, chosen already, and nothing is asked", () => {
    const choices = riverChoices(ONE_OF_EACH);
    expect(choices.exchanges).toEqual([{ id: 4, name: "Exchange", hidden: false }]);
    expect(choices.wallets).toEqual([{ id: 2, name: "Wallet", hidden: false }]);
    expect(choices.defaults).toEqual({ exchange: 4, wallet: 2 });
    expect([choices.askExchange, choices.askWallet]).toEqual([false, false]);
  });

  it("with more than one, are asked, hidden ones too, the first shown wallet chosen (Q8), each exchange by its name", () => {
    const choices = riverChoices(MANY, "River");
    expect(choices.exchanges).toEqual([
      { id: 4, name: "River", hidden: false }, { id: 103, name: "Kraken", hidden: false },
      { id: 106, name: "Closed", hidden: true },
    ]);
    expect(choices.wallets).toEqual([
      { id: 2, name: "Sparrow", hidden: false }, { id: 100, name: "Coldcard", hidden: false },
      { id: 104, name: "Old phone", hidden: true },
    ]);
    expect(choices.defaults).toEqual({ exchange: 4, wallet: 2 });
    expect([choices.askExchange, choices.askWallet]).toEqual([true, true]);
    // Only the kind with more than one is asked
    const secondWallet = [...ONE_OF_EACH, { ...ONE_OF_EACH[1], id: 100, name: "Coldcard" }];
    expect([riverChoices(secondWallet).askExchange, riverChoices(secondWallet).askWallet]).toEqual([false, true]);
  });

  it("never default to a hidden one: the first shown is chosen, and the screen still asks", () => {
    // Your first exchange hidden and Kraken shown: a file isn't sent to Kraken unasked (the review of #355)
    const choices = riverChoices(hide(MANY, [2, 3, 4]), "River");
    expect(choices.defaults).toEqual({ exchange: undefined, wallet: 100 });
    expect(choices.exchanges.map((e) => e.id)).toEqual([4, 103, 106]);
    expect([choices.askExchange, choices.askWallet]).toEqual([true, true]);
  });

  it("with every one of a kind hidden, ask with none chosen", () => {
    const choices = riverChoices(hide(MANY, [2, 100]), "River");
    expect(choices.defaults).toEqual({ exchange: 4, wallet: undefined });
    expect(choices.wallets.map((w) => w.id)).toEqual([2, 100, 104]);
    expect(choices.askWallet).toBe(true);
    // One wallet, hidden: still asked, so it isn't taken unasked
    expect(riverChoices(hide(ONE_OF_EACH, [2])).askWallet).toBe(true);
  });

  it("of more than one exchange, take none unasked, but the one shown the file is named for (#707)", () => {
    expect(riverChoices(MANY).defaults).toEqual({ exchange: undefined, wallet: 2 });
    expect(riverChoices(MANY, "").defaults.exchange).toBeUndefined();
    expect(riverChoices(MANY, "Coinbase").defaults.exchange).toBeUndefined();
    expect(riverChoices(MANY, " kraken ").defaults.exchange).toBe(103);
    // A ready-made mapping's name for one of an exchange's files
    expect(riverChoices(MANY, "Kraken: ledger").defaults.exchange).toBe(103);
    expect(riverChoices(MANY, "Krakenite").defaults.exchange).toBeUndefined();
    // Never a hidden one, even by its name
    expect(riverChoices(MANY, "Closed").defaults.exchange).toBeUndefined();
    // Two named alike: neither taken
    const twice = MANY.map((a) => (a.exchange === "Closed" ? { ...a, exchange: "kraken", hidden: false } : a));
    expect(riverChoices(twice, "Kraken").defaults.exchange).toBeUndefined();
    // With one exchange, it's taken whatever the file's name, as before
    expect(riverChoices(ONE_OF_EACH, "Coinbase").defaults).toEqual({ exchange: 4, wallet: 2 });
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
  it("is the owner's while that account is there, else the default; nothing before the book is read", () => {
    const choices = riverChoices(MANY, "River");
    expect(chosenRiverAccounts(choices, {})).toEqual({ exchange: 4, wallet: 2 });
    expect(chosenRiverAccounts(riverChoices(MANY), {})).toEqual({ exchange: undefined, wallet: 2 });
    expect(chosenRiverAccounts(choices, { exchange: 103 })).toEqual({ exchange: 103, wallet: 2 });
    // Kraken hidden since it was picked: still the pick, so a preview made with it stands
    expect(chosenRiverAccounts(riverChoices(hide(MANY, [102, 103])), { exchange: 103 }))
      .toEqual({ exchange: 103, wallet: 2 });
    // Deleted since: back to the default (two exchanges left: the one the file is named for)
    const gone = MANY.filter((a) => a.exchange_id !== 2);
    expect(chosenRiverAccounts(riverChoices(gone, "River"), { exchange: 103 })).toEqual({ exchange: 4, wallet: 2 });
    expect(chosenRiverAccounts(undefined, { exchange: 103 })).toEqual({});
  });
});

describe("a preview made with one pick", () => {
  it("is out of date once the pick differs, never for one made before the book was read", () => {
    expect(previewOutOfDate({ exchange: 103, wallet: 100 }, { exchange: 103, wallet: 100 })).toBe(false);
    expect(previewOutOfDate({ exchange: 103, wallet: 100 }, { exchange: 4, wallet: 100 })).toBe(true);
    expect(previewOutOfDate({ exchange: 103, wallet: 100 }, { exchange: 103, wallet: 2 })).toBe(true);
    // Sent without ids, the server took your first ones: what the book then picks says nothing about it
    expect(previewOutOfDate({}, { exchange: 4, wallet: 2 })).toBe(false);
    expect(previewOutOfDate(null, { exchange: 4, wallet: 2 })).toBe(false);
  });
});

describe("a pick", () => {
  it("is wanting while the screen asks and one of the two isn't chosen (every one hidden, no exchange named)", () => {
    expect(pickNeeded(riverChoices(MANY), { exchange: 4, wallet: 2 })).toBeUndefined();
    expect(pickNeeded(riverChoices(MANY), { exchange: 4 })).toBe("Choose the wallet first.");
    // The exchange first, as the screen asks them (#773)
    expect(pickNeeded(riverChoices(MANY), {})).toBe("Choose the exchange first.");
    // Before the book is read nothing is sent, and the server takes your first ones
    expect(pickNeeded(undefined, {})).toBeUndefined();
  });
});
