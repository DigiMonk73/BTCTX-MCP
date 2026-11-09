// A page whose session ended, for the tests of where it goes (#919): the
// server's answers, and the page's address, whose leaving for another page is
// recorded rather than done (jsdom loads no other page).
import { AxiosError, type AxiosAdapter, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { vi } from "vitest";

/** The page at `path`: the addresses it's sent to, in order. Undone by
 * vi.unstubAllGlobals(). */
export function pageAt(path: string): string[] {
  const sentTo: string[] = [];
  const go = (url: string | URL) => {
    sentTo.push(String(url));
  };
  vi.stubGlobal("location", {
    origin: "http://localhost",
    pathname: path,
    get href() {
      return `http://localhost${path}`;
    },
    set href(url: string) {
      go(url);
    },
    assign: go,
    replace: go,
  });
  return sentTo;
}

/** The server, answering each request with `answer`'s status and body: an
 * error status rejects, as axios's own adapters do. */
export function answers(answer: (config: InternalAxiosRequestConfig) => [number, unknown]): AxiosAdapter {
  return async (config) => {
    const [status, data] = answer(config);
    const response = { data, status, statusText: "", headers: {}, config } as AxiosResponse;
    if (status < 400) return response;
    throw new AxiosError(`Request failed with status code ${status}`, "ERR_BAD_REQUEST", config, null, response);
  };
}

/** The 401 of a session that ended (backend/main.py, get_current_user). */
export const NOT_AUTHENTICATED: [number, unknown] = [401, { detail: "Not authenticated" }];
