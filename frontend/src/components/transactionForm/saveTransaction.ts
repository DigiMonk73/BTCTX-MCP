import axios from "axios";
import api from "../../api";
import { formatUsd, parseDecimal } from "../../utils/format";
import { buildTransactionPayload } from "../../utils/transactionForm";

/**
 * Save the form: a new transaction, or `transactionId`'s changes. Returns
 * the message to show, with the realized gain when there is one.
 */
export async function saveTransaction(data: TransactionFormData, transactionId?: number | null): Promise<string> {
  const payload = buildTransactionPayload(data);
  if (transactionId) {
    const response = await api.put(`/transactions/${transactionId}`, payload);
    if (response.status !== 200) {
      throw new Error(`Update failed with status ${response.status}`);
    }
    return savedMessage("updated", response.data as ITransactionRaw);
  }
  const response = await api.post("/transactions", payload);
  return savedMessage("created", response.data as ITransactionRaw);
}

function savedMessage(done: "created" | "updated", tx: ITransactionRaw): string {
  const rg = tx.realized_gain_usd ? parseDecimal(tx.realized_gain_usd) : 0;
  if (rg !== 0) {
    const sign = rg >= 0 ? "+" : "";
    return `Transaction ${done}! Realized Gain: ${sign}${formatUsd(rg)}`;
  }
  return `Transaction ${done} successfully!`;
}

/** Why the save failed: the server's reason when it gave one. */
export function saveFailedMessage(error: unknown, action: "create" | "update"): string {
  if (axios.isAxiosError<ApiErrorResponse>(error)) {
    const detailMsg = error.response?.data?.detail || error.message || "Error";
    return `Failed to ${action} transaction: ${detailMsg}`;
  }
  if (error instanceof Error) {
    return `Failed to ${action} transaction: ${error.message}`;
  }
  return `An unexpected error occurred while ${action}ing the transaction.`;
}
