// The transaction form mounted as the panel mounts it (spec 5.13: the round trip
// on the mounted form, with its fill-ins), against a stubbed server that answers
// from an account book. Every request is recorded, in order.
import "./setup";
import { act, render } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { AxiosError, type AxiosRequestConfig, type AxiosResponse } from "axios";
import { vi } from "vitest";
import api from "../api";
import TransactionForm from "../components/TransactionForm";
import { ToastProvider } from "../contexts/ToastContext";

export interface SentRequest {
  method: "get" | "post" | "put" | "delete";
  url: string;
  body?: unknown;
  /** The query string's values (`?confirm=…`), when a write sent any. */
  params?: Record<string, unknown>;
}

/** The past-year warning (spec 5.8) as the stub answers it. */
export interface PastYearsStub {
  years: number[];
  /** The fingerprints of its 409s, in turn: confirmed with the last, a write saves. Two of them: the ledger
   * changed between the first 409 and its confirm, so the confirm gets a new 409. Default ["fp-1"]. */
  fingerprints?: string[];
  pending?: object[];
}

export interface RenderFormOptions {
  book: AccountBook;
  /** A saved row to edit: answered at GET /transactions/{id}, and the form opens on it. */
  transaction?: ITransactionRaw;
  /** GET /accounts/ answers 500 (D4). */
  accountsFail?: boolean;
  /** GET /accounts/ waits for answerAccounts(), so every other answer comes first. */
  accountsHeld?: boolean;
  /** Every write (an add, an edit, a delete) changes these earlier tax years: it answers 409 until confirmed. */
  pastYears?: PastYearsStub;
}

export interface RenderedForm {
  user: UserEvent;
  requests: SentRequest[];
  /** Click Save, then wait until every request it made has its answer. */
  save: () => Promise<void>;
  /** With accountsHeld: let GET /accounts/ answer, and wait for what follows. */
  answerAccounts: () => Promise<void>;
  /** Delete the row being edited (the panel's Delete, "Are you sure?" answered yes), then wait for the answers. */
  remove: () => Promise<void>;
  /** Let every answer, and the renders they cause, run. */
  settle: () => Promise<void>;
}

/** The sentence and the one changed row the stub's 409 carries (the server's words, 5.8). */
export function pastYearsBody(years: number[], confirm: string, pending: object[] = []): object {
  const several = years.length > 1;
  const text = several ? `tax years ${years.slice(0, -1).join(", ")} and ${years[years.length - 1]}` : `tax year ${years[0]}`;
  return {
    detail: `This changes the figures of ${text}, which you may already have filed. ` +
      "Confirm to save it: a copy of your ledger is made first.",
    years,
    changes: [{
      id: 7, date: `${years[0]}-03-01 12:00`, type: "Withdrawal", purpose: "Spent", source: null,
      amount: "0.50000000", unit: "BTC", accounts: ["Wallet"], change: "gain 10000.00 -> 5000.00.", years,
    }],
    pending,
    recalc_error: null,
    confirm,
  };
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

/** The past-year warning's 409 for a write, or null once it's confirmed with the last fingerprint. */
function pastYearsRefusal(stub: PastYearsStub, request: SentRequest): AxiosError | null {
  const fingerprints = stub.fingerprints ?? ["fp-1"];
  const confirm = request.params?.confirm;
  const at = typeof confirm === "string" ? fingerprints.indexOf(confirm) + 1 : 0;
  if (at === fingerprints.length) return null;
  const response = answer(pastYearsBody(stub.years, fingerprints[at], stub.pending), 409);
  return new AxiosError("Request failed with status code 409", "ERR_BAD_REQUEST", undefined, undefined, response);
}

/** The stubbed server: what each read answers, and a saved row for each write. */
function serve(options: RenderFormOptions, request: SentRequest): Promise<AxiosResponse> {
  const { method, url, body } = request;
  const refused = method !== "get" && options.pastYears ? pastYearsRefusal(options.pastYears, request) : null;
  if (refused) return Promise.reject(refused);
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

/** Every api call goes to `serve`, recorded first; the account list after `held`, when given. */
function stubApi(
  options: RenderFormOptions,
  requests: SentRequest[],
  pending: Set<Promise<unknown>>,
  held?: Promise<void>,
): void {
  const call = (request: SentRequest) => {
    requests.push(request);
    if (held && request.url === "/accounts/") return held.then(() => serve(options, request));
    const reply = serve(options, request);
    const tracked = reply.catch(() => undefined).finally(() => pending.delete(tracked));
    pending.add(tracked);
    return reply;
  };
  // A write's ?confirm= (5.8) is recorded only when it's sent, so the other tests' requests read as before
  const withParams = (request: SentRequest, config?: AxiosRequestConfig) =>
    call(config?.params ? { ...request, params: config.params as Record<string, unknown> } : request);
  vi.spyOn(api, "get").mockImplementation((url: string) => call({ method: "get", url }));
  vi.spyOn(api, "delete").mockImplementation((url: string, config?: AxiosRequestConfig) =>
    withParams({ method: "delete", url }, config));
  vi.spyOn(api, "post").mockImplementation((url: string, body?: unknown, config?: AxiosRequestConfig) =>
    withParams({ method: "post", url, body }, config));
  vi.spyOn(api, "put").mockImplementation((url: string, body?: unknown, config?: AxiosRequestConfig) =>
    withParams({ method: "put", url, body }, config));
}

/** Mount the form with `book` (and `transaction` to edit), its first answers in. */
export async function renderForm(options: RenderFormOptions): Promise<RenderedForm> {
  forgetAccounts();
  const requests: SentRequest[] = [];
  const pending = new Set<Promise<unknown>>();
  let release = () => {};
  const held = options.accountsHeld ? new Promise<void>((resolve) => (release = resolve)) : undefined;
  stubApi(options, requests, pending, held);
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
  const answerAccounts = async () => {
    release();
    await settle(pending);
  };
  const remove = async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await act(async () => {
      document.querySelector<HTMLButtonElement>("#trigger-form-delete")?.click();
    });
    await settle(pending);
  };
  return { user, requests, save, answerAccounts, remove, settle: () => settle(pending) };
}
