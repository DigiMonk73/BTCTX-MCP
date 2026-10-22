// The Transactions page (B8, spec 5.13) mounted against a stubbed server that
// answers GET /transactions with `rows` and GET /accounts/ with `book`.
import "./setup";
import { act, render, type RenderResult } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { vi } from "vitest";
import api from "../api";
import { ToastProvider } from "../contexts/ToastContext";
import Transactions from "../pages/Transactions";
import { forgetAccounts } from "../utils/useAccounts";

export interface RenderTransactionsOptions {
  book: AccountBook;
  rows: ITransactionRaw[];
  /** GET /accounts/ answers 500 (D4). */
  accountsFail?: boolean;
}

function answer<T>(data: T, status = 200): AxiosResponse<T> {
  return { data, status, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

/** A saved row as GET /transactions gives it: what a list row reads, the rest blank. */
export function savedRow(
  id: number, type: TransactionType, from: number | null, to: number | null, amount: string,
  extra: Partial<ITransactionRaw> = {},
): ITransactionRaw {
  return {
    id, type, from_account_id: from, to_account_id: to, amount, fee_amount: "0", fee_currency: "BTC",
    timestamp: `2024-06-${String(id).padStart(2, "0")}T12:00:00Z`, cost_basis_usd: "0", realized_gain_usd: "0",
    ...extra,
  } as ITransactionRaw;
}

/** Mount the page, its first answers in. */
export async function renderTransactions(options: RenderTransactionsOptions): Promise<{ view: RenderResult; user: UserEvent }> {
  forgetAccounts();
  vi.spyOn(api, "get").mockImplementation((url: string) => {
    if (url === "/accounts/") {
      return options.accountsFail
        ? Promise.reject(new AxiosError("Request failed with status code 500", "ERR_BAD_RESPONSE", undefined, undefined,
          answer({ detail: "stub: /accounts/ answers 500" }, 500)))
        : Promise.resolve(answer(options.book));
    }
    if (url === "/transactions") return Promise.resolve(answer(options.rows));
    return Promise.reject(new Error(`stub: no answer for GET ${url}`));
  });
  const user = userEvent.setup();
  const view = render(<ToastProvider><Transactions /></ToastProvider>);
  for (let round = 0; round < 5; round += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
  return { view, user };
}
