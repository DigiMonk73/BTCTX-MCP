// The River import's preview rows as the owner edits them, and the import
// request built from them.
import type { InputPlace } from "./apiError";

/** The file's exchange (its bitcoin account) and wallet, by the names the
 * import reads (2.0 spec 5.11, 5.13): a row's type change keeps them. */
export interface RiverAccounts {
  exchange: string;
  wallet: string;
}

/** Your first exchange's and wallet's: what any file's names mean with one of each (1.x's). */
export const FIRST_RIVER_ACCOUNTS: RiverAccounts = { exchange: "Exchange BTC", wallet: "Wallet" };

/** One preview row plus the owner's edits. */
export interface EditableRow {
  proposal: RiverProposal;
  /** The file's exchange and wallet, as chosen for its preview. */
  accounts: RiverAccounts;
  include: boolean;
  type: string;
  fromAccount: string;
  toAccount: string;
  costBasisUsd: string;
  feeAmount: string;
  purpose: string;
  source: string;
}

export const WITHDRAWAL_PURPOSES = ["Spent", "Gift", "Donation", "Lost"];
export const DEPOSIT_SOURCES = ["MyBTC", "Gift", "Income", "Interest", "Reward", "Rebate"];

export const STATUS_LABEL: Record<RiverProposal["status"], string> = {
  new: "New",
  matched: "In ledger",
  discrepancy: "Review",
};

/** A preview row as it starts: ticked unless it's already in the ledger,
 * or matched only by a near amount, most likely the same move typed by hand
 * (a row of the same amount to review is never left out by itself, #253). */
export function toEditableRow(p: RiverProposal, accounts: RiverAccounts = FIRST_RIVER_ACCOUNTS): EditableRow {
  return {
    proposal: p,
    accounts,
    include: p.status === "new" || (p.status === "discrepancy" && !p.near_amount),
    type: p.type,
    fromAccount: p.from_account,
    toAccount: p.to_account,
    costBasisUsd: p.cost_basis_usd != null ? String(p.cost_basis_usd) : "",
    feeAmount: p.fee_amount != null ? String(p.fee_amount) : "",
    purpose: p.purpose ?? "Spent",
    source: p.source ?? "MyBTC",
  };
}

/** Accounts implied by a type flip on a BTC move (direction-aware): the
 * file's exchange and wallet, never the first ones (5.13). */
function accountsForType(row: EditableRow, newType: string) {
  const { exchange, wallet } = row.accounts;
  const isSend = row.proposal.from_account === exchange;
  if (newType === "Withdrawal") return { from: exchange, to: "External" };
  if (newType === "Deposit") return { from: "External", to: exchange };
  // Transfer
  return isSend ? { from: exchange, to: wallet } : { from: wallet, to: exchange };
}

/** The edit a new type makes: the type and the accounts it implies. */
export function typeChange(row: EditableRow, newType: string): Partial<EditableRow> {
  const accounts = accountsForType(row, newType);
  return { type: newType, fromAccount: accounts.from, toAccount: accounts.to };
}

/** An exchange or a wallet a River file can be from or send to. */
export interface RiverChoice {
  /** An exchange's bitcoin account, or the wallet. */
  id: number;
  /** The exchange's name ("Kraken"), or the wallet's. */
  name: string;
  hidden: boolean;
}

export interface RiverChoices {
  exchanges: RiverChoice[];
  wallets: RiverChoice[];
  /** The first wallet shown (Q8's), and the only exchange if it's shown, or
   * of more than one, the one shown that the file is named for; none
   * otherwise (every one of its kind hidden, or no exchange named so). */
  defaults: { exchange?: number; wallet?: number };
  /** Whether the screen asks: more than one to choose from, or none chosen. */
  askExchange: boolean;
  askWallet: boolean;
}

/** What River's "Exchange" and "Wallet for sends and receives" offer (5.11,
 * 5.13): every exchange and wallet, hidden ones too, since they're still
 * yours; asked once there's more than one, so a file never goes to the only
 * one shown unasked; the first shown wallet chosen, never a hidden one. Of
 * more than one exchange, none is chosen but the one shown that the file
 * (`fileExchange`: "River", a mapping's name) is named for: 1.x's guide had
 * a second exchange's trades recorded in the first, so a file taken there
 * unasked holds them twice (the owner's decision, 2026-10-25, #707). */
export function riverChoices(book: AccountBook, fileExchange?: string): RiverChoices {
  const choice = (a: LedgerAccount, name: string) => ({ id: a.id, name, hidden: a.hidden });
  const exchanges = book.filter((a) => a.kind === "exchange" && a.currency === "BTC")
    .map((a) => choice(a, a.exchange ?? a.name));
  const wallets = book.filter((a) => a.kind === "wallet").map((a) => choice(a, a.name));
  const exchange = exchanges.length > 1 ? namedFor(exchanges, fileExchange) : exchanges.find((c) => !c.hidden)?.id;
  const wallet = wallets.find((c) => !c.hidden)?.id;
  return {
    exchanges, wallets,
    defaults: { exchange, wallet },
    askExchange: exchanges.length > 1 || exchange === undefined,
    askWallet: wallets.length > 1 || wallet === undefined,
  };
}

/** The one exchange shown that the file's is named for, ignoring case: "Swan"
 * for "Swan: withdrawals", as ready-made mappings are named. */
function namedFor(exchanges: RiverChoice[], fileExchange: string | undefined): number | undefined {
  const file = fileExchange?.trim().toLowerCase();
  if (!file) return undefined;
  const named = exchanges.filter((c) => {
    const name = c.name.trim().toLowerCase();
    return !c.hidden && (file === name || file.startsWith(`${name}:`));
  });
  return named.length === 1 ? named[0].id : undefined;
}

/** The file's exchange (its bitcoin account) and wallet, by id; undefined: none chosen. */
export interface RiverPick {
  exchange?: number;
  wallet?: number;
}

/** The file's exchange and wallet: the owner's pick while that account is
 * there (hidden since, it stays: a preview made with it still names it),
 * else riverChoices' default. Nothing before the book is read: the server
 * then takes your first exchange and wallet. */
export function chosenRiverAccounts(choices: RiverChoices | undefined, picked: RiverPick): RiverPick {
  if (!choices) return {};
  const offeredId = (id: number | undefined, list: RiverChoice[]) => (list.some((c) => c.id === id) ? id : undefined);
  return {
    exchange: offeredId(picked.exchange, choices.exchanges) ?? choices.defaults.exchange,
    wallet: offeredId(picked.wallet, choices.wallets) ?? choices.defaults.wallet,
  };
}

/** Whether the file can't be previewed yet: the book read, and an exchange
 * or a wallet not chosen (every one of its kind hidden, so none is preselected). */
export function pickWanting(choices: RiverChoices | undefined, pick: RiverPick): boolean {
  return choices !== undefined && (pick.exchange === undefined || pick.wallet === undefined);
}

/** Whether the preview on screen was made with another exchange or wallet
 * than the one picked now (its account deleted since): its rows would then
 * go elsewhere than the pickers say. One made before the book was read sent
 * no ids, so it's never compared. */
export function previewOutOfDate(made: RiverPick | null, now: RiverPick): boolean {
  if (!made || made.exchange === undefined) return false;
  return made.exchange !== now.exchange || made.wallet !== now.wallet;
}

/** The chosen exchange and wallet by the names the import reads; the first ones' until the book is read. */
export function riverAccountNames(book: AccountBook | undefined, chosen: RiverPick): RiverAccounts {
  const name = (id: number | undefined) => book?.find((a) => a.id === id)?.name;
  return {
    exchange: name(chosen.exchange) ?? FIRST_RIVER_ACCOUNTS.exchange,
    wallet: name(chosen.wallet) ?? FIRST_RIVER_ACCOUNTS.wallet,
  };
}

/** The rows to import: the ticked ones, a row already in the ledger
 * included when the owner ticks it (#253). */
export function importableRows(rows: EditableRow[]): EditableRow[] {
  return rows.filter((r) => r.include);
}

/** The import request's rows: the ticked ones, and each one the preview
 * found in the ledger left unticked (`left_out`, never imported), as the
 * preview gave it, so an edit left in it can't stop the import. Each row
 * found in the ledger carries the transaction it matched, which the server
 * keeps for it, so an identical row beside it isn't taken for it, whatever
 * the owner edited (#253). */
export function importRequestRows(rows: EditableRow[]) {
  return rows
    .filter((r) => r.include || r.proposal.status === "matched")
    .map((r) => importRow(r.include ? r : toEditableRow(r.proposal, r.accounts)));
}

/** A fee's currency: USD on a Buy or Sell, BTC otherwise (River's rows say so too). */
function feeCurrency(r: EditableRow): "USD" | "BTC" {
  return r.type === "Buy" || r.type === "Sell" ? "USD" : "BTC";
}

/** The fee as the preview shows it, with its unit as the other columns are: "$1.50", "0.00000200 BTC". */
export function feeText(r: EditableRow): string {
  if (!r.feeAmount) return "—";
  return feeCurrency(r) === "USD" ? `$${r.feeAmount}` : `${r.feeAmount} BTC`;
}

/** A row of the import request: the fee in feeCurrency's currency; only a
 * Deposit has a source and only a Withdrawal a purpose. */
export function importRow(r: EditableRow) {
  return {
    // The file's row number, which the import's errors name, as the preview did (#455)
    row_number: r.proposal.row_number,
    date: r.proposal.date,
    type: r.type,
    amount: r.proposal.amount,
    from_account: r.fromAccount,
    to_account: r.toAccount,
    cost_basis_usd: r.costBasisUsd || null,
    proceeds_usd: r.proposal.proceeds_usd ?? null,
    fee_amount: r.feeAmount || null,
    fee_currency: r.feeAmount ? feeCurrency(r) : null,
    source: r.type === "Deposit" ? r.source : null,
    purpose: r.type === "Withdrawal" ? r.purpose : null,
    // The preview's value from the price, left as it was: not typed, so an
    // edit of the deposit prices it again (#76); and the price's moment
    cost_basis_typed: basisFromPrice(r) ? "no" : null,
    price_moment: basisFromPrice(r) ? (r.proposal.price_moment ?? null) : null,
    // Found in the ledger: the transaction it matched, kept for it; ticked,
    // it's another transaction, so the import's check for a second click
    // lets it through (#253)
    matched_tx_id: r.proposal.status === "matched" ? (r.proposal.matched_tx_id ?? null) : null,
    not_a_duplicate: r.include && r.proposal.status === "matched",
    left_out: !r.include,
  };
}

function basisFromPrice(r: EditableRow): boolean {
  return Boolean(r.proposal.basis_autofilled) && r.costBasisUsd === String(r.proposal.cost_basis_usd);
}

/** An import row's fields, by the preview's column heads. */
const COLUMN_HEADS = new Map([
  ["date", "Date"],
  ["type", "Type"],
  ["from_account", "From → To"],
  ["to_account", "From → To"],
  ["amount", "Amount"],
  ["cost_basis_usd", "Cost Basis"],
  ["proceeds_usd", "Proceeds (before fee)"],
  ["fee_amount", "Fee"],
]);

/** Where in the file a cell the server refused is (#480). Its 422 places
 * the cell among the rows sent (["body", "rows", i, field]), which aren't
 * the file's rows, so the place is the row's number in the file (the
 * header is row 1, as the preview's lists and the import's other refusals
 * number rows) and the cell's column, "Row 6 (Cost Basis)"; for a field
 * no column shows, the row alone. */
export function refusedCellPlace(sent: { row_number: number }[]): InputPlace {
  return ([where, list, index, field]) => {
    const row = where === "body" && list === "rows" && typeof index === "number" ? sent[index] : undefined;
    if (!row) return null;
    const column = typeof field === "string" ? COLUMN_HEADS.get(field) : undefined;
    return column ? `Row ${row.row_number} (${column})` : `Row ${row.row_number}`;
  };
}
