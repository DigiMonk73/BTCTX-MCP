// The transaction form mounted as the panel mounts it (spec 5.13: the round trip
// on the mounted form, with its fill-ins), against a stubbed server that answers
// from an account book. Every request is recorded, in order.
import "./setup";
import { act, render } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { AxiosError, type AxiosResponse } from "axios";
import { vi } from "vitest";
import api from "../api";
import TransactionForm from "../components/TransactionForm";
import { ToastProvider } from "../contexts/ToastContext";

export interface SentRequest {
  method: "get" | "post" | "put" | "delete";
  url: string;
  body?: unknown;
}

export interface RenderFormOptions {
  book: AccountBook;
  /** A saved row to edit: answered at GET /transactions/{id}, and the form opens on it. */
  transaction?: ITransactionRaw;
  /** GET /accounts/ answers 500 (D4). */
  accountsFail?: boolean;
}

export interface RenderedForm {
  user: UserEvent;
  requests: SentRequest[];
  /** Click Save, then wait until every request it made has its answer. */
  save: () => Promise<void>;
}

// The price hint's two reads (useBlankPriceSource): a fresh install's, so the
// hints keep their first sentence and nothing else is asked
const PRICE_STATUS = { history: null };
const NETWORK = { price_source: "unset", mempool_url: null, mempool_fallback: false, proxy_url: null };

// B6a-4 adds useAccounts.ts; until then there's no cache to forget. A glob, not an
// import, so the helper compiles before that file exists
const accountHooks = import.meta.glob<{ forgetAccounts?: () => void }>("../utils/useAccounts.ts", { eager: true });

function forgetAccounts(): void {
  for (const hooks of Object.values(accountHooks)) hooks.forgetAccounts?.();
}

function answer<T>(data: T, status = 200): AxiosResponse<T> {
  return { data, status, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

function failure(url: string, status: number): AxiosError {
  const response = answer({ detail: `stub: ${url} answers ${status}` }, status);
  return new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_RESPONSE", undefined, undefined, response);
}

/** The stubbed server: what each read answers, and a saved row for each write. */
function serve(options: RenderFormOptions, request: SentRequest): Promise<AxiosResponse> {
  const { method, url, body } = request;
  if (method === "get" && url === "/accounts/") {
    return options.accountsFail ? Promise.reject(failure(url, 500)) : Promise.resolve(answer(options.book));
  }
  if (method === "get" && url === "/bitcoin/price/status") return Promise.resolve(answer(PRICE_STATUS));
  if (method === "get" && url === "/settings/network") return Promise.resolve(answer(NETWORK));
  const saved = options.transaction;
  if (method === "get" && saved && url === `/transactions/${saved.id}`) return Promise.resolve(answer(saved));
  if (method === "post" && url === "/transactions") return Promise.resolve(answer({ id: 1, ...(body as object) }));
  if (method === "put" && saved && url === `/transactions/${saved.id}`) {
    return Promise.resolve(answer({ ...saved, ...(body as object) }));
  }
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
  vi.spyOn(api, "get").mockImplementation((url: string) => call({ method: "get", url }));
  vi.spyOn(api, "delete").mockImplementation((url: string) => call({ method: "delete", url }));
  vi.spyOn(api, "post").mockImplementation((url: string, body?: unknown) => call({ method: "post", url, body }));
  vi.spyOn(api, "put").mockImplementation((url: string, body?: unknown) => call({ method: "put", url, body }));
}

/** Mount the form with `book` (and `transaction` to edit), its first answers in. */
export async function renderForm(options: RenderFormOptions): Promise<RenderedForm> {
  forgetAccounts();
  const requests: SentRequest[] = [];
  const pending = new Set<Promise<unknown>>();
  stubApi(options, requests, pending);
  const user = userEvent.setup();
  const view = render(
    <ToastProvider>
      <TransactionForm id="transaction-form" transactionId={options.transaction?.id} />
      <button type="submit" form="transaction-form">Save transaction</button>
    </ToastProvider>,
  );
  await settle(pending);
  const save = async () => {
    await user.click(view.getByRole("button", { name: "Save transaction" }));
    await settle(pending);
  };
  return { user, requests, save };
}
