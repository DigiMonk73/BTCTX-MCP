// The account book, loaded once per page (spec 5.4): every form and list on the
// page shares one GET /api/accounts/.
import { useEffect, useState } from "react";
import api from "../api";

/** What a screen shows in place of its account fields when the book won't load (D4). */
export const ACCOUNTS_FAILED = "Couldn't load your accounts: reload the page.";

export interface AccountsState {
  book?: AccountBook; // undefined until loaded
  failed: boolean;
}

let loading: Promise<AccountBook> | undefined;

/** The page's one request; a failed one is asked again by the next screen that mounts. */
function loadAccounts(): Promise<AccountBook> {
  if (loading) return loading;
  const request = api.get<AccountBook>("/accounts/").then((res) => res.data);
  loading = request;
  // A rejection clears this request only while it is still the one stored.
  // forgetAccounts may have started a newer one; that one stays.
  request.catch(() => {
    if (loading === request) loading = undefined;
  });
  return request;
}

/** The next useAccounts() asks the server again: Settings calls it after adding,
 * renaming, hiding or deleting an account (B7b), and tests between cases. */
export function forgetAccounts(): void {
  loading = undefined;
}

export function useAccounts(): AccountsState {
  const [state, setState] = useState<AccountsState>({ failed: false });
  useEffect(() => {
    // An unmounted screen sets no state.
    let live = true;
    loadAccounts().then(
      (book) => {
        if (live) setState({ book, failed: false });
      },
      () => {
        if (live) setState({ failed: true });
      },
    );
    return () => {
      live = false;
    };
  }, []);
  return state;
}
