// A bitcoin withdrawal's proceeds in the edit form: what it shows for a
// saved one, and what a save sends, as the server reads them
// (`_withdrawal_gross_proceeds` and `_apply_proceeds` in
// backend/services/transaction.py).
import { optionalDecimal } from "./format";
import { isNotSold } from "./purposes";

// The server's bitcoin accounts: Wallet, Exchange BTC
const BTC_ACCOUNT_IDS = [2, 4];

/**
 * A saved withdrawal's proceeds as the form edits them: the user's gross
 * (stored proceeds_usd is net of a Spent's BTC fee). A gift, donation or lost
 * coins, or a dollar withdrawal, has none: a $0 an older form saved shows
 * blank, so making it a Spent prices it at the hour (#457); a former spend's
 * shows. A row saved before the gross was kept has none (parsed as 0): it
 * shows the gross the server recovers for it, so saving it unchanged keeps
 * it (#485). A Spent's $0 is a $0 it was given; another purpose with none
 * stored doesn't say what it received (#329): blank.
 */
export function withdrawalProceeds(tx: ITransaction): number | undefined {
  if (!BTC_ACCOUNT_IDS.includes(tx.from_account_id ?? 0)) return undefined;
  if (tx.gross_proceeds_usd) return tx.gross_proceeds_usd;
  if (isNotSold(tx.purpose)) return undefined;
  if ((tx.proceeds_usd ?? 0) > 0) return recoveredGross(tx);
  return (tx.purpose ?? "").trim().toLowerCase() === "spent" ? 0 : undefined;
}

/**
 * The gross the server recovers for a row with none and proceeds above $0: a
 * Spent's stored net had its BTC fee's offset taken off (versions before
 * 0.9.2), undone over the amount and the fee; another purpose's had none
 * (#61), an old " spent " included (#342: to those versions a purpose they
 * didn't know).
 */
function recoveredGross(tx: ITransaction): number {
  const net = tx.proceeds_usd ?? 0;
  const fee = tx.fee_currency?.toUpperCase() === "BTC" ? (tx.fee_amount ?? 0) : 0;
  const offsetTaken = tx.purpose?.toLowerCase() === "spent" && fee > 0 && tx.amount > 0;
  return offsetTaken ? Number(((net * (tx.amount + fee)) / tx.amount).toFixed(2)) : net;
}

/** What a save sends as a bitcoin withdrawal's proceeds: a Spent's (blank is
 * null: that hour's price); for any other purpose none (#457). */
export function proceedsSent(data: TransactionFormData): number | null | undefined {
  return data.purpose === "Spent" ? optionalDecimal(data.proceeds_usd) : undefined;
}
