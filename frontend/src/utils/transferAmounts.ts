// A transfer's two amounts: the dollar fee between them (#447) and what the
// form refuses in them, kept apart from the form's mapping
// (transactionForm.ts) so each stays one job.
import { accountCurrency, chosenId } from "./accounts";
import { parseDecimal } from "./format";

/** A dollar transfer's fee: what left less what arrived, in cents (#447). */
export function dollarTransferFee(amountFrom: number, amountTo: number): number {
  return (Math.round(amountFrom * 100) - Math.round(amountTo * 100)) / 100;
}

/** More than 2 decimal places: a dollar amount the server refuses. Compared
 * as written to the cent, not as amount × 100, whose float error passes any
 * fixed tolerance in the hundreds of millions. */
export function pastTheCent(amount: number): boolean {
  return Number.isFinite(amount) && Number(amount.toFixed(2)) !== amount;
}

/**
 * What's wrong with a transfer's Amount (From) or Amount (To), in words; null
 * if nothing. What arrived is never more than what left (the difference is
 * the fee, #447), a move within one BTC account records only its fee, so
 * there must be one (#159), and dollars are in cents: Amount (From) isn't
 * sent, so the server can't say so for it. A dollar transfer's Amount (To)
 * is the amount saved, so it must be more than 0.
 */
export function transferAmountProblem(
  data: Pick<TransactionFormData, "fromAccountId" | "toAccountId" | "amountFrom" | "amountTo">,
  book: AccountBook,
  field: "amountFrom" | "amountTo",
): string | null {
  const from = parseDecimal(data.amountFrom);
  const to = parseDecimal(data.amountTo);
  const fromId = chosenId(data.fromAccountId);
  const currency = accountCurrency(book, fromId);
  if (currency === "USD" && pastTheCent(parseDecimal(data[field]))) {
    return "A USD amount can have at most 2 decimal places.";
  }
  if (field === "amountFrom") return null;
  if (to > from) {
    return "Amount (To) can't be more than Amount (From): it's what arrived, Amount (From) less the fee.";
  }
  if (currency === "USD" && !(to > 0)) return "Amount (To) must be more than 0.";
  if (currency === "BTC" && chosenId(data.toAccountId) === fromId && !(to < from)) {
    return "A consolidation within the same wallet or exchange records only its network fee: Amount (To) must be less than Amount (From).";
  }
  return null;
}
