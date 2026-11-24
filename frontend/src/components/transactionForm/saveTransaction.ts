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

/** What the form says once a save went through. */
export interface Saved {
  message: string;
  /** Set when this device's timezone rules read the typed time otherwise than the server's (#964). */
  warning?: string;
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
): Promise<Saved> {
  const payload = buildTransactionPayload(data, book);
  let tx: ITransactionRaw;
  if (transactionId) {
    const response = await api.put(`/transactions/${transactionId}`, payload, withConfirm(confirm));
    if (response.status !== 200) {
      throw new Error(`Update failed with status ${response.status}`);
    }
    tx = response.data as ITransactionRaw;
  } else {
    tx = (await api.post("/transactions", payload, withConfirm(confirm))).data as ITransactionRaw;
  }
  const warning = deviceRulesWarning(payload, tx.timestamp);
  return { message: savedMessage(transactionId ? "updated" : "created", tx), ...(warning ? { warning } : {}) };
}

/**
 * When the server read a typed time as another moment than this device
 * did (#964), what to tell the owner: the time typed is the one saved,
 * and this device shows it off by the difference until its rules are
 * updated. Undefined when they agree, or nothing was typed.
 */
export function deviceRulesWarning(payload: ICreateTransactionPayload, savedTimestamp: string): string | undefined {
  if (!payload.typed_time) return undefined;
  const minutes = Math.round((Date.parse(payload.timestamp) - Date.parse(savedTimestamp)) / 60_000);
  if (!minutes) return undefined;
  return `Saved at the time you typed. This device's timezone rules are out of date, so it shows this ` +
    `transaction's time ${howFar(minutes)} off until its system or browser is updated.`;
}

function howFar(minutes: number): string {
  const all = Math.abs(minutes);
  if (all === 60) return "an hour";
  if (all % 60 === 0) return `${all / 60} hours`;
  return all > 60 ? `${Math.floor(all / 60)} h ${all % 60} min` : `${all} minutes`;
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
