// Settings' "Wallets, exchanges and banks" (2.0 spec 5.9; P7's mockups, #572):
// its rows and texts, worked out from the account book. Pure: no React, no api.
import { formatBtc, formatUsd, parseDecimal } from "./format";

/** The kinds the owner adds (5.1): never a fee account. */
export type YourKind = "bank" | "wallet" | "exchange";

/** One row: a bank's or a wallet's account, or an exchange's two (its dollars, then its bitcoin). */
export interface AccountRow {
  key: string;
  kind: YourKind;
  /** The account's name, or the exchange's ("Kraken" for "Kraken USD" and "Kraken BTC"). */
  name: string;
  accounts: LedgerAccount[];
  /** An exchange's two are hidden and shown together (5.1). */
  hidden: boolean;
  /** A transaction or a ledger line names it (an exchange: either account). */
  inUse: boolean;
  /** The account the API's Hide, Show and Delete take: for an exchange, either of its two does both. */
  id: number;
}

export interface AccountGroup {
  kind: YourKind;
  title: string;
  add: string;
  shown: AccountRow[];
  hidden: AccountRow[];
}

const GROUPS: { kind: YourKind; title: string }[] = [
  { kind: "wallet", title: "Wallets" },
  { kind: "exchange", title: "Exchanges" },
  { kind: "bank", title: "Banks" },
];

export const ADD_LABEL: Record<YourKind, string> = {
  wallet: "Add a wallet",
  exchange: "Add an exchange",
  bank: "Add a bank",
};

export const KIND_LABEL: Record<YourKind, string> = { wallet: "Wallet", exchange: "Exchange", bank: "Bank" };

// Your first bank, wallet and exchange (decision 4: their ids never change),
// which the API never deletes (services/account.FIRST_OF_EACH): hidden instead
const FIRST_OF_EACH = new Set([1, 2, 3, 4]);

/** The section's rows by kind, each kind's in the book's order, the hidden ones apart. */
export function accountGroups(book: AccountBook): AccountGroup[] {
  const rows = accountRows(book);
  return GROUPS.map(({ kind, title }) => {
    const ofKind = rows.filter((row) => row.kind === kind);
    return {
      kind, title, add: ADD_LABEL[kind],
      shown: ofKind.filter((row) => !row.hidden),
      hidden: ofKind.filter((row) => row.hidden),
    };
  });
}

function accountRows(book: AccountBook): AccountRow[] {
  const rows: AccountRow[] = [];
  for (const account of book) {
    if (account.kind === "fee") continue;
    if (account.kind !== "exchange" || account.exchange_id === null) {
      rows.push(row(`account-${account.id}`, account.kind, account.name, [account]));
      continue;
    }
    if (rows.some((r) => r.key === `exchange-${account.exchange_id}`)) continue;
    const pair = book
      .filter((a) => a.kind === "exchange" && a.exchange_id === account.exchange_id)
      .sort((a, b) => (a.currency === b.currency ? 0 : a.currency === "USD" ? -1 : 1));
    rows.push(row(`exchange-${account.exchange_id}`, "exchange", account.exchange ?? account.name, pair));
  }
  return rows;
}

function row(key: string, kind: YourKind, name: string, accounts: LedgerAccount[]): AccountRow {
  return {
    key, kind, name, accounts,
    hidden: accounts.every((a) => a.hidden),
    inUse: accounts.some((a) => a.in_use),
    id: accounts[accounts.length - 1].id,
  };
}

/** The section's element ids: its buttons name what they open by them, and
 * the keyboard goes back to them after a change. */
export const ledgerIds = {
  rowToggle: (key: string) => `ledger-account-${key}-toggle`,
  rowDetails: (key: string) => `ledger-account-${key}`,
  group: (kind: YourKind) => `ledger-group-${kind}`,
  addButton: (kind: YourKind) => `ledger-group-${kind}-add-button`,
  addForm: (kind: YourKind) => `ledger-group-${kind}-add`,
  showHidden: (kind: YourKind) => `ledger-group-${kind}-show-hidden`,
  hiddenList: (kind: YourKind) => `ledger-group-${kind}-hidden`,
};

/** Delete is offered only for an account nothing names, and never your first bank, wallet or exchange (5.9). */
export function canDelete(row: AccountRow): boolean {
  return !row.inUse && !row.accounts.some((a) => FIRST_OF_EACH.has(a.id));
}

/** A row's balance in its currency ("$250.00", "0.25000000 BTC"; an exchange's
 * dollars, then its bitcoin); "" until the balances have come, or for an
 * account they don't list. */
export function balanceText(row: AccountRow, balances: AccountBalance[] | undefined): string {
  const amounts = row.accounts.map((account) => {
    const found = balances?.find((b) => b.account_id === account.id);
    if (!found) return null;
    const amount = parseDecimal(found.balance);
    return account.currency === "USD" ? formatUsd(amount) : formatBtc(amount);
  });
  return amounts.every((a) => a !== null) ? amounts.join(" · ") : "";
}

/** The section's one-line summary: each kind shown, then the hidden ones ("2 wallets · 1 exchange · 1 bank · 1 hidden"). */
export function accountsSummary(book: AccountBook | undefined): string {
  if (!book) return "Your accounts, by kind";
  const groups = accountGroups(book);
  const parts = groups
    .filter((g) => g.shown.length > 0)
    .map((g) => `${g.shown.length} ${g.shown.length === 1 ? KIND_LABEL[g.kind].toLowerCase() : g.title.toLowerCase()}`);
  const hidden = groups.reduce((n, g) => n + g.hidden.length, 0);
  return [...parts, ...(hidden > 0 ? [`${hidden} hidden`] : [])].join(" · ");
}

// 5.9's words for each exchange's switch, exactly
export const SWITCH_LABEL = "This exchange sends me a Form 1099-DA";
export const SWITCH_HELP =
  "An exchange in the US sends one for your sales from 2025; one outside the US usually doesn't. " +
  "It decides the Form 8949 box, not the gain.";

/** An exchange's switch: on (the default, the owner's decision of 2026-10-15)
 * unless its accounts say off (they say the same: it's the exchange's); null
 * for a bank's or a wallet's row. */
export function sends1099da(row: AccountRow): boolean | null {
  if (row.kind !== "exchange") return null;
  return !row.accounts.some((a) => a.sends_1099da === false);
}

// 5.1's, 5.9's and 5.8's words (Q5's note with P6's sentence, #569), exactly: never reworded
export const WALLET_HELP =
  "A wallet is one set of keys: every address it makes is part of it. A backup of the same keys (a seed phrase, " +
  "or another device with the same keys) isn't a second wallet. If you use multiple wallets, add each one: since " +
  "2025 the IRS figures cost basis wallet by wallet.";

const exchangeHelp = (name: string) =>
  `BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, '${name} USD' and '${name} BTC'.`;

/** An exchange's help text before a name is typed. */
export const EXCHANGE_HELP = exchangeHelp("name");

const pooled = (kind: string, together: string, each: string) =>
  `Years before you add this ${kind} were figured with your ${together} together, as BitcoinTX 1.x did. Move ` +
  "coins into it with a Transfer dated when they really moved: BitcoinTX moves the oldest coins first. A " +
  "Transfer dated in an earlier year can change that year's figures and later ones (BitcoinTX shows which years " +
  `before it saves), and BitcoinTX doesn't allocate your cost basis to each ${each} as of January 1, 2025 ` +
  "(Rev. Proc. 2024-28), nor record an allocation you made: its figures from 2025 on follow its own history. A " +
  "tax professional can compare that with yours (your 2024 Complete Tax Report lists each account's lots at the " +
  "end of 2024) and tell you whether an earlier return needs a change.";

export const POOLED_NOTE: Record<"wallet" | "exchange", string> = {
  wallet: pooled("wallet", "wallets", "wallet"),
  exchange: pooled("exchange", "exchange accounts", "exchange account"),
};

/** A name as the server will keep it (5.1: each run of spaces one space, at the ends none). */
function keptName(name: string): string {
  return name.normalize("NFC").replace(/\p{Zs}+/gu, " ").replace(/^ | $/g, "");
}

/** The help text under the name when adding (5.1, 5.9): an exchange's with the
 * name as the server will keep it; none for a bank. */
export function addHelp(kind: YourKind, name: string): string | null {
  if (kind === "wallet") return WALLET_HELP;
  if (kind === "bank") return null;
  const shown = keptName(name);
  return shown ? exchangeHelp(shown) : EXCHANGE_HELP;
}

/** Q5's note (5.8) when adding a wallet (or an exchange) while another one,
 * hidden or not, has transactions: earlier years were figured with them
 * together. A new user's second wallet, before any transaction, gets none. */
export function pooledNote(book: AccountBook, kind: YourKind): string | null {
  if (kind === "bank") return null;
  return book.some((account) => account.kind === kind && account.in_use) ? POOLED_NOTE[kind] : null;
}

// Settings' Rename (#356, 2.0 spec 5.9 and 5.11's note on names in files)
export const RENAME_FILES_NOTE =
  "A CSV file names accounts as they're named when you import it: one saved before a rename still " +
  "names this account by its old name.";

/** Whether Rename has something to send: a name the server would keep that
 * isn't the row's (an exchange's row: the exchange's); its case counts. */
export function renameReady(row: AccountRow, typed: string): boolean {
  const kept = keptName(typed);
  return kept !== "" && kept !== row.name;
}

/** Under an exchange's new name, what its two accounts become, as Add says it; none for a bank or a wallet. */
export function renameHelp(row: AccountRow, typed: string): string | null {
  return row.kind === "exchange" ? addHelp("exchange", typed) : null;
}
