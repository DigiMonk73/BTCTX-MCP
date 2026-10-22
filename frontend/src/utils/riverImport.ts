// The River import's preview rows as the owner edits them, and the import
// request built from them.
import type { InputPlace } from "./apiError";

/** One preview row plus the owner's edits. */
export interface EditableRow {
  proposal: RiverProposal;
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
export function toEditableRow(p: RiverProposal): EditableRow {
  return {
    proposal: p,
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

/** Accounts implied by a type flip on a BTC move (direction-aware). */
function accountsForType(row: EditableRow, newType: string) {
  const isSend = row.proposal.from_account === "Exchange BTC";
  if (newType === "Withdrawal") return { from: "Exchange BTC", to: "External" };
  if (newType === "Deposit") return { from: "External", to: "Exchange BTC" };
  // Transfer
  return isSend
    ? { from: "Exchange BTC", to: "Wallet" }
    : { from: "Wallet", to: "Exchange BTC" };
}

/** The edit a new type makes: the type and the accounts it implies. */
export function typeChange(row: EditableRow, newType: string): Partial<EditableRow> {
  const accounts = accountsForType(row, newType);
  return { type: newType, fromAccount: accounts.from, toAccount: accounts.to };
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
    .map((r) => importRow(r.include ? r : toEditableRow(r.proposal)));
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
 * the file's rows, so the place is the file's row the preview showed and
 * the cell's column, "Row 6 (Cost Basis)"; for a field no column shows,
 * the row alone. */
export function refusedCellPlace(sent: { row_number: number }[]): InputPlace {
  return ([where, list, index, field]) => {
    const row = where === "body" && list === "rows" && typeof index === "number" ? sent[index] : undefined;
    if (!row) return null;
    const column = typeof field === "string" ? COLUMN_HEADS.get(field) : undefined;
    return column ? `Row ${row.row_number} (${column})` : `Row ${row.row_number}`;
  };
}
