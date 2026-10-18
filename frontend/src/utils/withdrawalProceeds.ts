// A bitcoin withdrawal's proceeds in the edit form: what it shows for a
// saved one, and what a save sends, as the server reads them
// (`_withdrawal_gross_proceeds` and `_apply_proceeds` in
// backend/services/transaction.py).
import { optionalDecimal } from "./format";
import { isNotSold, listedPurpose } from "./purposes";

/**
 * A saved bitcoin withdrawal's proceeds as the form edits them: the user's
 * gross (stored proceeds_usd is net of a Spent's BTC fee). A gift, donation
 * or lost coins has none: a $0 an older form saved shows blank, so making it
 * a Spent prices it (#457); a former spend's shows. A row saved before the
 * gross was kept has none (a blank gross reads as 0): it shows the gross the
 * server recovers for it, so saving it unchanged keeps it (#485).
 */
export function withdrawalProceeds(tx: ITransaction): number | undefined {
  if (tx.gross_proceeds_usd) return tx.gross_proceeds_usd;
  if (isNotSold(tx.purpose)) return undefined;
  return recoveredGross(tx);
}

/**
 * The gross the server works out for a row with none, as its next
 * recalculation does (a Spent's $0 has $0 proceeds too):
 * - a Spent (as the server spells it: an old " spent " isn't one, #342) with
 *   none stored at all is priced: blank, so the save prices it the same way;
 * - above $0, a Spent's stored net had its BTC fee's offset taken off
 *   (versions before 0.9.2), undone over the amount and the fee; another
 *   purpose's had none (#61);
 * - otherwise it received $0, or nothing BitcoinTX knows (#329): blank for a
 *   purpose the form doesn't list, which must be chosen before a save; $0
 *   for one it shows as Spent, so a save that changes nothing keeps it.
 */
function recoveredGross(tx: ITransaction): number | undefined {
  const spent = tx.purpose?.toLowerCase() === "spent";
  const net = tx.proceeds_usd;
  if (net === undefined && spent) return undefined;
  if (net === undefined || net <= 0) return listedPurpose(tx.purpose) === "Spent" ? 0 : undefined;
  const fee = tx.fee_currency?.toUpperCase() === "BTC" ? (tx.fee_amount ?? 0) : 0;
  return spent && fee > 0 && tx.amount > 0 ? offsetUndone(net, tx.amount, fee) : net;
}

/**
 * net x (amount + fee) / amount, to the cent, an exact half to even, as the
 * server's Decimal.quantize rounds it: in whole cents and satoshis, since a
 * float lands a cent off at a half (1.515 is 1.5149999…).
 */
function offsetUndone(net: number, amount: number, fee: number): number {
  const cents = BigInt(Math.round(net * 100));
  const sats = BigInt(Math.round(amount * 1e8));
  const whole = cents * (sats + BigInt(Math.round(fee * 1e8)));
  let rounded = whole / sats;
  const twiceLeft = 2n * (whole % sats);
  if (twiceLeft > sats || (twiceLeft === sats && rounded % 2n === 1n)) rounded += 1n;
  return Number(rounded) / 100;
}

/** What a save sends as a bitcoin withdrawal's proceeds: a Spent's (blank is
 * null: the server prices it); for any other purpose none (#457). */
export function proceedsSent(data: TransactionFormData): number | null | undefined {
  return data.purpose === "Spent" ? optionalDecimal(data.proceeds_usd) : undefined;
}
