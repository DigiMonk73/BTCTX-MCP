// The transaction form mounted as the panel mounts it (2.0 spec 5.13: the
// round trip on the mounted form, with its fill-ins), against a stubbed
// server that answers from an account book, or as a test says (the
// past-year warning's 409, #352). Every request is recorded, in order;
// nothing leaves the test.
import "./setup";
import { act, render, screen, within } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { AxiosError, type AxiosRequestConfig, type AxiosResponse } from "axios";
import { vi } from "vitest";
import api from "../api";
import TransactionForm from "../components/TransactionForm";
import { ToastProvider, type Toast } from "../contexts/ToastContext";
import { forgetQuietYears } from "../utils/pastYears";
import { forgetAccounts } from "../utils/useAccounts";
import ToastLog from "./ToastLog";

export interface SentRequest {
  method: "get" | "post" | "put" | "delete";
  url: string;
  body?: Record<string, unknown>;
  /** Its query parameters (the past-year warning's confirm) */
  params?: Record<string, unknown>;
}

/** A test's own answer: its status and body (400 and above, a failure). */
export interface PlannedAnswer {
  status: number;
  data: unknown;
}

export interface RenderFormOptions {
  book: AccountBook;
  /** A saved row to edit: answered at GET /transactions/{id}, and the form opens on it. */
  transaction?: Partial<ITransactionRaw> & { id: number; type: TransactionType };
  /** GET /accounts/ answers 500. */
  accountsFail?: boolean;
  /** Answers a request before the stub does; undefined leaves it to the stub. */
  respond?: (request: SentRequest) => PlannedAnswer | undefined;
}

export interface RenderedForm {
  user: UserEvent;
  requests: SentRequest[];
  /** Click Save, then wait until every request it made has its answer. */
  save: () => Promise<void>;
  /** The body of the last POST or PUT. */
  sent: () => Record<string, unknown> | undefined;
  /** The writes sent (POST, PUT and DELETE), in order. */
  writes: () => SentRequest[];
  /** Let every request made so far have its answer, and the form settle. */
  settle: () => Promise<void>;
  /** Every toast shown since the form was mounted, in order. */
  toasts: () => Pick<Toast, "type" | "message">[];
  /** Choose an option by its text in the select labelled `label`, and let the form settle. */
  choose: (label: string, option: string) => Promise<void>;
  /** Pick a type for a new transaction. */
  pickType: (type: TransactionType) => Promise<void>;
  unmount: () => void;
}

// The price hint's two reads (useBlankPriceSource): a fresh install's, so
// the hints keep their first sentence and nothing else is asked
const PRICE_STATUS = { history: null };
const NETWORK = { price_source: "unset", mempool_url: null, mempool_fallback: false, proxy_url: null };

function answer<T>(data: T, status = 200): AxiosResponse<T> {
  return { data, status, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

function failure(url: string, status: number, data: unknown = { detail: `stub: ${url} answers ${status}` }): AxiosError {
  const response = answer(data, status);
  return new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_RESPONSE", undefined, undefined, response);
}

/** A saved row as GET /transactions/{id} answers it: its decimals as strings, the rest as given. */
function savedRow(transaction: NonNullable<RenderFormOptions["transaction"]>): ITransactionRaw {
  return {
    timestamp: "2024-06-15T15:04:05Z",
    amount: "0", fee_amount: "0", fee_currency: "USD", cost_basis_usd: null, proceeds_usd: null,
    ...transaction,
  } as unknown as ITransactionRaw;
}

/** The stubbed server: the test's own answer when it gives one, else what
 * each read answers, and a saved row for each write (nothing for a delete). */
function serve(options: RenderFormOptions, request: SentRequest): Promise<AxiosResponse> {
  const planned = options.respond?.(request);
  if (planned) {
    return planned.status >= 400
      ? Promise.reject(failure(request.url, planned.status, planned.data))
      : Promise.resolve(answer(planned.data, planned.status));
  }
  const { method, url, body } = request;
  if (method === "get" && url === "/accounts/") {
    return options.accountsFail ? Promise.reject(failure(url, 500)) : Promise.resolve(answer(options.book));
  }
  if (method === "get" && url === "/bitcoin/price/status") return Promise.resolve(answer(PRICE_STATUS));
  if (method === "get" && url === "/settings/network") return Promise.resolve(answer(NETWORK));
  const saved = options.transaction;
  if (method === "get" && saved && url === `/transactions/${saved.id}`) return Promise.resolve(answer(savedRow(saved)));
  if (method === "post" && url === "/transactions") return Promise.resolve(answer({ id: 1, ...body }));
  if (method === "put" && saved && url === `/transactions/${saved.id}`) {
    return Promise.resolve(answer({ ...savedRow(saved), ...body }));
  }
  if (method === "delete" && saved && url === `/transactions/${saved.id}`) return Promise.resolve(answer(null, 204));
  return Promise.reject(failure(url, 404));
}

/** Answers are promises: let them, and the renders they cause, run until none is left. */
async function settle(pending: Set<Promise<unknown>>): Promise<void> {
  for (let round = 0; round < 20; round += 1) {
    await act(async () => {
      await Promise.allSettled([...pending]);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    if (pending.size === 0) return;
  }
}

/** Every api call goes to `serve`, recorded first. */
function stubApi(options: RenderFormOptions, requests: SentRequest[], pending: Set<Promise<unknown>>): void {
  const call = (request: SentRequest) => {
    requests.push(request);
    const reply = serve(options, request);
    const tracked = reply.catch(() => undefined).finally(() => pending.delete(tracked));
    pending.add(tracked);
    return reply;
  };
  type Body = Record<string, unknown>;
  const params = (config?: AxiosRequestConfig) => config?.params as Body | undefined;
  vi.spyOn(api, "get").mockImplementation((url: string) => call({ method: "get", url }));
  vi.spyOn(api, "delete").mockImplementation((url: string, config?: AxiosRequestConfig) =>
    call({ method: "delete", url, params: params(config) }));
  vi.spyOn(api, "post").mockImplementation((url: string, body?: unknown, config?: AxiosRequestConfig) =>
    call({ method: "post", url, body: body as Body, params: params(config) }));
  vi.spyOn(api, "put").mockImplementation((url: string, body?: unknown, config?: AxiosRequestConfig) =>
    call({ method: "put", url, body: body as Body, params: params(config) }));
}

/** Mount the form with `book` (and `transaction` to edit), its first answers in. */
export async function renderForm(options: RenderFormOptions): Promise<RenderedForm> {
  forgetAccounts();
  forgetQuietYears(); // a page as freshly loaded
  const requests: SentRequest[] = [];
  const pending = new Set<Promise<unknown>>();
  stubApi(options, requests, pending);
  const user = userEvent.setup();
  const shownToasts = new Map<string, Pick<Toast, "type" | "message">>();
  const logToasts = (toasts: Toast[]) => {
    for (const { id, type, message } of toasts) shownToasts.set(id, { type, message });
  };
  const view = render(
    <ToastProvider>
      <ToastLog onToasts={logToasts} />
      <TransactionForm id="transaction-form" transactionId={options.transaction?.id} />
      <button type="submit" form="transaction-form">Save transaction</button>
    </ToastProvider>,
  );
  await settle(pending);
  const choose = async (label: string, option: string) => {
    const select = screen.getByLabelText(label, { exact: true });
    await user.selectOptions(select, within(select).getByRole("option", { name: option }));
    await settle(pending);
  };
  return {
    user,
    requests,
    save: async () => {
      await user.click(screen.getByRole("button", { name: "Save transaction" }));
      await settle(pending);
    },
    sent: () => requests.filter((r) => r.method === "post" || r.method === "put").at(-1)?.body,
    writes: () => requests.filter((r) => r.method !== "get"),
    settle: () => settle(pending),
    toasts: () => [...shownToasts.values()],
    choose,
    pickType: (type) => choose("Transaction Type", type),
    unmount: view.unmount,
  };
}

/** A field's shown value: a select's chosen option's text, an input's value. */
export function shown(label: string): string {
  const field = screen.getByLabelText(label, { exact: true });
  if (field instanceof HTMLSelectElement) return field.selectedOptions[0]?.text ?? "";
  return (field as HTMLInputElement).value;
}

/** The options a select offers, its blank one left out, with their groups ("Wallets: Coldcard"). */
export function offered(label: string): string[] {
  const field = screen.getByLabelText(label, { exact: true }) as HTMLSelectElement;
  return [...field.options]
    .filter((option) => option.value !== "")
    .map((option) => {
      const group = option.parentElement instanceof HTMLOptGroupElement ? `${option.parentElement.label}: ` : "";
      return `${group}${option.text}`;
    });
}
