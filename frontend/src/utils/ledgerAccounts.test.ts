// Settings' "Wallets, exchanges and banks" (#355, 2.0 spec 5.9): its rows,
// grouped by kind, and its texts word for word.
import { describe, expect, it } from "vitest";
import { MANY, ONE_OF_EACH } from "../test/books";
import {
  ADD_LABEL, EXCHANGE_HELP, POOLED_NOTE, SWITCH_HELP, SWITCH_LABEL, WALLET_HELP, accountGroups, accountsSummary,
  addHelp, balanceText, canDelete, pooledNote, sends1099da,
} from "./ledgerAccounts";

/** These accounts named by a transaction or a ledger line (the test books name none). */
const used = (book: AccountBook, ids: number[]) => book.map((a) => (ids.includes(a.id) ? { ...a, in_use: true } : a));

/** A 1.x ledger in use, and more of each (src/test/books.ts) with Coldcard and Kraken's bitcoin in use. */
const BOOK = used(ONE_OF_EACH, [1, 2, 3, 4]);
const MORE = used(MANY, [1, 2, 3, 4, 100, 103]);

describe("the rows", () => {
  it("are grouped wallets, exchanges, banks, each with its Add button; never the fee accounts", () => {
    const groups = accountGroups(BOOK);
    expect(groups.map((g) => [g.title, g.add])).toEqual([
      ["Wallets", "Add a wallet"], ["Exchanges", "Add an exchange"], ["Banks", "Add a bank"],
    ]);
    expect(groups.map((g) => g.shown.map((r) => r.name))).toEqual([["Wallet"], ["Exchange"], ["Bank"]]);
    expect(groups.flatMap((g) => [...g.shown, ...g.hidden]).flatMap((r) => r.accounts.map((a) => a.id)))
      .toEqual([2, 3, 4, 1]);
  });

  it("show an exchange as one row of its two accounts, dollars first, by its own name", () => {
    const [, exchanges] = accountGroups(MORE);
    expect(exchanges.shown.map((r) => [r.name, r.accounts.map((a) => a.id)])).toEqual([
      ["River", [3, 4]], ["Kraken", [102, 103]],
    ]);
  });

  it("keep the book's order within a kind, and put hidden ones apart", () => {
    const [wallets, exchanges, banks] = accountGroups(MORE);
    expect(wallets.shown.map((r) => r.name)).toEqual(["Sparrow", "Coldcard"]);
    expect(wallets.hidden.map((r) => r.name)).toEqual(["Old phone"]);
    expect(exchanges.hidden.map((r) => r.name)).toEqual(["Closed"]);
    expect(banks.shown.map((r) => r.name)).toEqual(["Checking", "Savings"]);
  });

  it("an exchange is hidden when its accounts are, in use when either is", () => {
    // Kraken's dollars unused, its bitcoin in use
    const kraken = accountGroups(MORE)[1].shown[1];
    expect([kraken.hidden, kraken.inUse]).toEqual([false, true]);
    const gone: AccountBook = MORE.map((a) => (a.exchange_id === 2 ? { ...a, hidden: true } : a));
    expect(accountGroups(gone)[1].hidden.map((r) => r.name)).toEqual(["Kraken", "Closed"]);
    // Only one of the two hidden (never so through the API): shown, so it's never lost from view
    const half: AccountBook = MORE.map((a) => (a.id === 103 ? { ...a, hidden: true } : a));
    expect(accountGroups(half)[1].shown.map((r) => r.name)).toEqual(["River", "Kraken"]);
  });

  it("offer Delete only for an account no transaction names, never your first bank, wallet or exchange", () => {
    const rows = (book: AccountBook) => accountGroups(book).flatMap((g) => [...g.shown, ...g.hidden]);
    expect(rows(MORE).filter(canDelete).map((r) => r.name)).toEqual(["Old phone", "Closed", "Savings"]);
    expect(rows(MANY).filter(canDelete).map((r) => r.name))
      .toEqual(["Coldcard", "Old phone", "Kraken", "Closed", "Savings"]);
    expect(rows(ONE_OF_EACH).filter(canDelete)).toEqual([]);
  });
});

describe("a row's balance", () => {
  const balances: AccountBalance[] = [
    { account_id: 1, name: "Bank", currency: "USD", balance: "80000.00" },
    { account_id: 2, name: "Wallet", currency: "BTC", balance: "0.4999" },
    { account_id: 3, name: "Exchange USD", currency: "USD", balance: 1040 },
    { account_id: 4, name: "Exchange BTC", currency: "BTC", balance: "0.25" },
  ];

  it("is in the account's currency; an exchange's dollars, then its bitcoin", () => {
    const [wallets, exchanges, banks] = accountGroups(BOOK);
    expect(balanceText(wallets.shown[0], balances)).toBe("0.49990000 BTC");
    expect(balanceText(exchanges.shown[0], balances)).toBe("$1,040.00 · 0.25000000 BTC");
    expect(balanceText(banks.shown[0], balances)).toBe("$80,000.00");
  });

  it("is blank while the balances haven't come, or don't list it", () => {
    const [wallets, exchanges] = accountGroups(MORE);
    expect(balanceText(wallets.shown[0], undefined)).toBe("");
    expect(balanceText(exchanges.shown[1], balances)).toBe("");
  });
});

describe("the section's summary", () => {
  it("counts each kind shown, and the hidden ones", () => {
    expect(accountsSummary(BOOK)).toBe("1 wallet · 1 exchange · 1 bank");
    expect(accountsSummary(MORE)).toBe("2 wallets · 2 exchanges · 2 banks · 2 hidden");
    expect(accountsSummary(undefined)).toBe("Your accounts, by kind");
  });
});

describe("adding an account (5.1, 5.8, 5.9: their words, exactly)", () => {
  it("labels each kind's button", () => {
    expect(ADD_LABEL).toEqual({ wallet: "Add a wallet", exchange: "Add an exchange", bank: "Add a bank" });
  });

  it("explains a wallet, an exchange's two accounts by the name typed, and nothing for a bank", () => {
    expect(WALLET_HELP).toBe(
      "A wallet is one set of keys: every address it makes is part of it. A backup of the same keys (a seed " +
      "phrase, or another device with the same keys) isn't a second wallet. If you use multiple wallets, add each " +
      "one: since 2025 the IRS figures cost basis wallet by wallet.",
    );
    expect(addHelp("wallet", "")).toBe(WALLET_HELP);
    expect(addHelp("exchange", "  Kraken   Pro ")).toBe(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'Kraken Pro USD' and 'Kraken Pro BTC'.",
    );
    expect(addHelp("exchange", " ")).toBe(EXCHANGE_HELP);
    // As the server keeps a name: runs of spaces (a no-break one too) made one; a tab isn't a space
    expect(addHelp("exchange", "Kraken\u00a0 Pro")).toContain("'Kraken Pro USD'");
    expect(addHelp("exchange", "Kraken\tPro")).toContain("'Kraken\tPro USD'");
    expect(EXCHANGE_HELP).toBe(
      "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'name USD' and 'name BTC'.",
    );
    expect(addHelp("bank", "Savings")).toBeNull();
  });

  it("gives Q5's note for a second wallet or exchange while another one has transactions", () => {
    expect(POOLED_NOTE.wallet).toBe(
      "Years before you add this wallet were figured with your wallets together, as BitcoinTX 1.x did. Move " +
      "coins into it with a Transfer dated when they really moved: BitcoinTX moves the oldest coins first. A " +
      "Transfer dated in an earlier year can change that year's figures and later ones (BitcoinTX shows which " +
      "years before it saves), and BitcoinTX doesn't allocate your cost basis to each wallet as of January 1, " +
      "2025 (Rev. Proc. 2024-28), nor record an allocation you made: its figures from 2025 on follow its own " +
      "history. A tax professional can compare that with yours (your 2024 Complete Tax Report lists each " +
      "account's lots at the end of 2024) and tell you whether an earlier return needs a change.",
    );
    expect(POOLED_NOTE.exchange).toBe(
      "Years before you add this exchange were figured with your exchange accounts together, as BitcoinTX 1.x " +
      "did. Move coins into it with a Transfer dated when they really moved: BitcoinTX moves the oldest coins " +
      "first. A Transfer dated in an earlier year can change that year's figures and later ones (BitcoinTX " +
      "shows which years before it saves), and BitcoinTX doesn't allocate your cost basis to each exchange " +
      "account as of January 1, 2025 (Rev. Proc. 2024-28), nor record an allocation you made: its figures from " +
      "2025 on follow its own history. A tax professional can compare that with yours (your 2024 Complete Tax " +
      "Report lists each account's lots at the end of 2024) and tell you whether an earlier return needs a change.",
    );
    expect(pooledNote(BOOK, "wallet")).toBe(POOLED_NOTE.wallet);
    expect(pooledNote(BOOK, "exchange")).toBe(POOLED_NOTE.exchange);
    expect(pooledNote(BOOK, "bank")).toBeNull();
  });

  it("gives no note while no other one of that kind has transactions (a new user's second wallet)", () => {
    const fresh = ONE_OF_EACH;
    expect(pooledNote(fresh, "wallet")).toBeNull();
    expect(pooledNote(fresh, "exchange")).toBeNull();
    // A hidden wallet with transactions still had its coins figured with the others
    const hiddenUsed = fresh.map((a) => (a.id === 2 ? { ...a, hidden: true, in_use: true } : a));
    expect(pooledNote(hiddenUsed, "wallet")).toBe(POOLED_NOTE.wallet);
    // Only the exchange's own accounts count, never a bank's dollars
    const bankUsed = fresh.map((a) => (a.id === 1 ? { ...a, in_use: true } : a));
    expect(pooledNote(bankUsed, "exchange")).toBeNull();
  });
});

describe("an exchange's 1099-DA switch (5.9)", () => {
  it("is in 5.9's words", () => {
    expect(SWITCH_LABEL).toBe("This exchange sends me a Form 1099-DA");
    expect(SWITCH_HELP).toBe(
      "An exchange in the US sends one for your sales from 2025; one outside the US usually doesn't. " +
      "It decides the Form 8949 box, not the gain.",
    );
  });

  it("is on unless the exchange's accounts say off, and is only an exchange's", () => {
    const [wallets, exchanges] = accountGroups(MANY);
    expect(sends1099da(exchanges.shown[0])).toBe(true); // a book from before the switch: on, the default
    const off = MANY.map((a) => (a.exchange_id === 2 ? { ...a, sends_1099da: false } : { ...a, sends_1099da: true }));
    expect(accountGroups(off)[1].shown.map((r) => [r.name, sends1099da(r)])).toEqual([["River", true], ["Kraken", false]]);
    expect(sends1099da(wallets.shown[0])).toBeNull();
  });
});
