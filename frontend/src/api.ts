import axios from "axios";
import { API_BASE_URL } from "./config";

// Every request says which page sent it (2.0 spec 5.13): the server refuses a
// browser's change from a page older than 2.0, which would save a Buy or Sell
// into the first exchange
const PAGE_HEADERS = { "X-BitcoinTX-Page": __BTCTX_VERSION__ };

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: true, // Include session cookie in all requests
  headers: PAGE_HEADERS,
});

const SIGN_IN_PAGE = "/login";
// The pages anyone may open: a 401 there is the page's own to show, and the
// sign-in page sent to itself would only load again
const SIGNED_OUT_PAGES = [SIGN_IN_PAGE, "/logout", "/register"];
// Requests whose 401 is their caller's answer, not an ended session: the
// sign-in's wrong password, and PrivateRoute's question whether anyone is
// signed in (it goes to the sign-in page itself)
const OWN_401 = [`${API_BASE_URL}/login`, `${API_BASE_URL}/protected`];
// How many pages hold the sign-in page off for now (holdSignIn)
let holds = 0;

/**
 * Keep this page where it is at an ended session's 401 while it shows what
 * the owner must read first: a restore signs this browser out and waits for
 * its notice to be read (BackupRestore, #407). Returns the release, for an
 * effect's cleanup, so a hold never outlives what it was for: one that stuck
 * would leave a signed-out page showing only errors (#919).
 */
export function holdSignIn(): () => void {
  holds += 1;
  let held = true;
  return () => {
    if (held) holds -= 1;
    held = false;
  };
}

/**
 * A signed-in page whose session ended (logged out in another browser, a
 * password change: SECURITY-RULES.md, "Sessions") goes to the sign-in page
 * at its next request's 401, rather than show load errors (#919). It's
 * loaded afresh, so nothing of the ended page stays: its figures, a toast
 * its failed request raised. The error still reaches the page that asked:
 * if the owner stays (the browser asks first while a form has unsaved
 * changes), the page says what failed.
 */
function toSignInWhenEnded(error: unknown): Promise<never> {
  if (holds === 0 && sessionEnded(error)) window.location.replace(SIGN_IN_PAGE);
  return Promise.reject(error);
}

/** Whether a failed request says this signed-in page's session ended. */
function sessionEnded(error: unknown): boolean {
  if (!axios.isAxiosError(error) || error.response?.status !== 401 || !error.config) return false;
  const path = new URL(axios.getUri(error.config), window.location.origin).pathname;
  return !OWN_401.includes(path) && !SIGNED_OUT_PAGES.includes(window.location.pathname);
}

api.interceptors.response.use(undefined, toSignInWhenEnded);

export async function downloadPdfWithAxios(
  url: string,
  onProgress?: (percent: number) => void
): Promise<Blob> {
  const response = await axios
    .get(url, {
      responseType: "blob",
      headers: PAGE_HEADERS,
      onDownloadProgress: (evt) => {
        if (evt.total && onProgress) {
          const percent = Math.floor((evt.loaded / evt.total) * 100);
          onProgress(percent);
        }
      },
    })
    .catch(toSignInWhenEnded);
  return response.data; // This is your PDF blob
}

export default api;
