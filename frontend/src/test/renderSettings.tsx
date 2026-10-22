// Settings' "Wallets, exchanges and banks" (B7b, spec 5.9) mounted as the page
// mounts it, with the page's message line, against a stubbed server that keeps
// an account book and changes it as the account API would (B7b-0, B8-5r's renames). Every request is
// recorded, in order.
import "./setup";
import React, { useState } from "react";
import { act, render, type RenderResult } from "@testing-library/react";
import userEvent, { type UserEvent } from "@testing-library/user-event";
import { AxiosError, type AxiosRequestConfig, type AxiosResponse } from "axios";
import { vi } from "vitest";
import api from "../api";

export interface SettingsRequest {
  method: "get" | "post" | "put" | "delete";
  url: string;
  body?: unknown;
  /** The query string's values (`?confirm=…`), as axios takes them. */
  params?: Record<string, unknown>;
}

export interface Refusal {
  status: number;
  body: object;
}

export interface RenderSettingsOptions {
  book: AccountBook;
  /** GET /calculations/accounts/balances; none listed when left out. */
  balances?: AccountBalance[];
  /** GET /accounts/ answers 500 (D4). */
  accountsFail?: boolean;
  /** A write's answer by "<method> <url>" ("delete /accounts/1"), in place of the stub's success. */
  refuse?: Record<string, Refusal>;
  /** Earlier tax years an exchange's 1099-DA switch would change (B6c's stub of 5.8):
   * a PUT of `sends_1099da` without `?confirm=` answers 409 with them. */
  pastYears?: number[];
}

export interface RenderedSettings {
  view: RenderResult;
  user: UserEvent;
  requests: SettingsRequest[];
  /** The stub's book now, after the writes it took. */
  book: () => AccountBook;
  /** Let every answer, and the renders they cause, run. */
  settle: () => Promise<void>;
}

/** The fingerprint the stub's 409 asks to be sent back. */
export const CONFIRM = "fp-1";

// The section's file comes with B7b-1. A glob, not an import, so this helper
// compiles (and every test says why it fails) before that file exists
const sections = import.meta.glob<{ default: React.FC<SettingsSectionProps> }>(
  "../components/LedgerAccounts.tsx", { eager: true },
);

const accountHooks = import.meta.glob<{ forgetAccounts?: () => void }>("../utils/useAccounts.ts", { eager: true });

function answer<T>(data: T, status = 200): AxiosResponse<T> {
  return { data, status, statusText: "OK", headers: {}, config: {} as AxiosResponse["config"] };
}

function refusal(status: number, body: object): AxiosError {
  return new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_RESPONSE", undefined, undefined,
    answer(body, status));
}

function yearsText(years: number[]): string {
  if (years.length === 1) return `tax year ${years[0]}`;
  return `tax years ${years.slice(0, -1).join(", ")} and ${years[years.length - 1]}`;
}

/** The stub's account book, changed by each write as the server changes its own (B7b-0). */
class Server {
  book: LedgerAccount[];

  constructor(private readonly options: RenderSettingsOptions) {
    this.book = options.book.map((a) => ({ ...a }));
  }

  halves(id: number): LedgerAccount[] {
    const account = this.book.find((a) => a.id === id);
    if (!account) return [];
    return account.exchange_id === null ? [account] : this.book.filter((a) => a.exchange_id === account.exchange_id);
  }

  add(kind: AccountKind, name: string): LedgerAccount[] {
    const id = Math.max(99, ...this.book.map((a) => a.id)) + 1;
    const blank = { exchange_id: null, exchange: null, sends_1099da: null, hidden: false, in_use: false };
    let made: LedgerAccount[];
    if (kind === "exchange") {
      const exchange = { exchange_id: Math.max(0, ...this.book.map((a) => a.exchange_id ?? 0)) + 1, exchange: name };
      made = [
        { ...blank, ...exchange, id, name: `${name} USD`, kind, currency: "USD", sends_1099da: true },
        { ...blank, ...exchange, id: id + 1, name: `${name} BTC`, kind, currency: "BTC", sends_1099da: true },
      ];
    } else {
      made = [{ ...blank, id, name, kind, currency: kind === "bank" ? "USD" : "BTC" }];
    }
    const order: AccountKind[] = ["bank", "wallet", "exchange", "fee"];
    this.book = [...this.book, ...made].sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind) || a.id - b.id);
    return made;
  }

  put(id: number, body: Partial<LedgerAccount>, params?: Record<string, unknown>): Promise<AxiosResponse> {
    const halves = this.halves(id);
    if (!halves.length) return Promise.reject(refusal(404, { detail: "Account not found." }));
    const years = this.options.pastYears ?? [];
    if (body.sends_1099da !== undefined && years.length && params?.confirm !== CONFIRM) {
      return Promise.reject(refusal(409, {
        detail: `This changes the figures of ${yearsText(years)}, which you may already have filed. ` +
          "Confirm to save it: a copy of your ledger is made first.",
        years, changes: [], pending: [], confirm: CONFIRM,
      }));
    }
    const { name, ...rest } = body;
    // A rename (B8-5r): an exchange's account renames its exchange and both its accounts
    if (name !== undefined) {
      for (const half of halves) {
        if (half.exchange_id === null) half.name = name;
        else Object.assign(half, { name: `${name} ${half.currency}`, exchange: name });
      }
    }
    for (const half of halves) Object.assign(half, rest);
    return Promise.resolve(answer(halves));
  }

  serve(request: SettingsRequest): Promise<AxiosResponse> {
    const { method, url, body, params } = request;
    const refused = this.options.refuse?.[`${method} ${url}`];
    if (refused) return Promise.reject(refusal(refused.status, refused.body));
    const id = Number(url.match(/^\/accounts\/(\d+)$/)?.[1]);
    if (method === "get" && url === "/accounts/") {
      return this.options.accountsFail
        ? Promise.reject(refusal(500, { detail: "stub: /accounts/ answers 500" }))
        : Promise.resolve(answer(this.book.map((a) => ({ ...a }))));
    }
    if (method === "get" && url === "/calculations/accounts/balances") {
      return Promise.resolve(answer(this.options.balances ?? []));
    }
    if (method === "post" && url === "/accounts/") {
      const { kind, name } = body as { kind: AccountKind; name: string };
      return Promise.resolve(answer(this.add(kind, name), 201));
    }
    if (method === "put" && id) return this.put(id, body as Partial<LedgerAccount>, params);
    if (method === "delete" && id) {
      const gone = new Set(this.halves(id).map((a) => a.id));
      this.book = this.book.filter((a) => !gone.has(a.id));
      return Promise.resolve(answer(null, 204));
    }
    return Promise.reject(refusal(404, { detail: `stub: no answer for ${method} ${url}` }));
  }
}

/** Settings' section with the page's state and message line around it, as `pages/Settings.tsx` has them. */
// eslint-disable-next-line react-refresh/only-export-components -- a test helper, never hot-reloaded
function Page({ Section }: { Section: React.FC<SettingsSectionProps> }) {
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  return (
    <div>
      <Section loading={loading} setLoading={setLoading} setMessage={setMessage} />
      {message && <p className="note settings-message" role="status">{message}</p>}
    </div>
  );
}

async function settle(pending: Set<Promise<unknown>>): Promise<void> {
  for (let round = 0; round < 20; round += 1) {
    await act(async () => {
      await Promise.allSettled([...pending]);
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    if (pending.size === 0) return;
  }
}

function stubApi(server: Server, requests: SettingsRequest[], pending: Set<Promise<unknown>>): void {
  const call = (request: SettingsRequest) => {
    requests.push(request);
    const reply = server.serve(request);
    const tracked = reply.catch(() => undefined).finally(() => pending.delete(tracked));
    pending.add(tracked);
    return reply;
  };
  const params = (config?: AxiosRequestConfig) => config?.params as Record<string, unknown> | undefined;
  vi.spyOn(api, "get").mockImplementation((url: string) => call({ method: "get", url }));
  vi.spyOn(api, "delete").mockImplementation((url: string) => call({ method: "delete", url }));
  vi.spyOn(api, "post").mockImplementation((url: string, body?: unknown) => call({ method: "post", url, body }));
  vi.spyOn(api, "put").mockImplementation((url: string, body?: unknown, config?: AxiosRequestConfig) =>
    call({ method: "put", url, body, ...(params(config) ? { params: params(config) } : {}) }));
}

/** Mount the section on `book`, its first answers in. */
export async function renderSettings(options: RenderSettingsOptions): Promise<RenderedSettings> {
  const Section = Object.values(sections)[0]?.default;
  if (!Section) throw new Error("LedgerAccounts.tsx isn't built yet (B7b-1)");
  for (const hooks of Object.values(accountHooks)) hooks.forgetAccounts?.();
  const server = new Server(options);
  const requests: SettingsRequest[] = [];
  const pending = new Set<Promise<unknown>>();
  stubApi(server, requests, pending);
  const user = userEvent.setup();
  const view = render(<Page Section={Section} />);
  await settle(pending);
  return { view, user, requests, book: () => server.book, settle: () => settle(pending) };
}
