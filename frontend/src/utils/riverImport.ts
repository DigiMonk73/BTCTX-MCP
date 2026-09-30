// The River import's preview rows as the owner edits them, and the import
// request built from them.

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
export const DEPOSIT_SOURCES = ["MyBTC", "Gift", "Income", "Interest", "Reward"];

export const STATUS_LABEL: Record<RiverProposal["status"], string> = {
  new: "New",
  matched: "In ledger",
  discrepancy: "Review",
};

/** A preview row as it starts: only new rows are ticked for import. */
export function toEditableRow(p: RiverProposal): EditableRow {
  return {
    proposal: p,
    include: p.status === "new",
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

/** The rows to import: ticked, and not already in the ledger. */
export function importableRows(rows: EditableRow[]): EditableRow[] {
  return rows.filter((r) => r.include && r.proposal.status !== "matched");
}

/** A row of the import request. A fee is in USD on a Buy or Sell and in BTC
 * otherwise; only a Deposit has a source and only a Withdrawal a purpose. */
export function importRow(r: EditableRow) {
  return {
    date: r.proposal.date,
    type: r.type,
    amount: r.proposal.amount,
    from_account: r.fromAccount,
    to_account: r.toAccount,
    cost_basis_usd: r.costBasisUsd || null,
    proceeds_usd: r.proposal.proceeds_usd ?? null,
    fee_amount: r.feeAmount || null,
    fee_currency: r.feeAmount ? (r.type === "Buy" || r.type === "Sell" ? "USD" : "BTC") : null,
    source: r.type === "Deposit" ? r.source : null,
    purpose: r.type === "Withdrawal" ? r.purpose : null,
  };
}
