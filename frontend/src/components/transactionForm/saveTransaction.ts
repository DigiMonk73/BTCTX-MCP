import axios, { type AxiosRequestConfig } from "axios";
import api from "../../api";
import { serverReason } from "../../utils/apiError";
import { formatUsd, parseDecimal } from "../../utils/format";
import { buildTransactionPayload } from "../../utils/transactionForm";

/** A write sent again with the past-year warning's confirm (#352); as
 * always without one. */
export function withConfirm(confirm?: string): AxiosRequestConfig | undefined {
  return confirm ? { params: { confirm } } : undefined;
}

/**
 * Save the form: a new transaction, or `transactionId`'s changes, with
 * `confirm` once the owner confirmed a change to an earlier tax year.
 * Returns the message to show, with the realized gain when there is one.
 */
export async function saveTransaction(
  data: TransactionFormData,
  book: AccountBook,
  transactionId?: number | null,
  confirm?: string,
): Promise<string> {
  const payload = buildTransactionPayload(data, book);
  if (transactionId) {
    const response = await api.put(`/transactions/${transactionId}`, payload, withConfirm(confirm));
    if (response.status !== 200) {
      throw new Error(`Update failed with status ${response.status}`);
    }
    return savedMessage("updated", response.data as ITransactionRaw);
  }
  const response = await api.post("/transactions", payload, withConfirm(confirm));
  return savedMessage("created", response.data as ITransactionRaw);
}

/** Delete `transactionId`, with `confirm` once the owner confirmed a change to an earlier tax year. */
export async function deleteTransaction(transactionId: number, confirm?: string): Promise<void> {
  await api.delete(`/transactions/${transactionId}`, withConfirm(confirm));
}

function savedMessage(done: "created" | "updated", tx: ITransactionRaw): string {
  const rg = tx.realized_gain_usd ? parseDecimal(tx.realized_gain_usd) : 0;
  if (rg !== 0) {
    const sign = rg >= 0 ? "+" : "";
    return `Transaction ${done}! Realized Gain: ${sign}${formatUsd(rg)}`;
  }
  return `Transaction ${done} successfully!`;
}

/** Why the save failed: the server's reason when it gave one, a 422's list
 * in its words (#448). */
export function saveFailedMessage(error: unknown, action: "create" | "update"): string {
  if (axios.isAxiosError(error)) {
    return `Failed to ${action} transaction: ${serverReason(error) || error.message || "Error"}`;
  }
  if (error instanceof Error) {
    return `Failed to ${action} transaction: ${error.message}`;
  }
  return `An unexpected error occurred while ${action}ing the transaction.`;
}
