// The account book, loaded once per page (2.0 spec 5.4): every form and
// list on the page shares one GET /api/accounts/, until Settings asks again
// (as it opens, and after it changes an account: useSettingsAccounts).
import { useEffect, useState } from "react";
import api from "../api";

/** What a screen shows in place of its account fields when the book won't load. */
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
  // Only while it is still the one kept: forgetAccounts may have started a newer one
  request.catch(() => {
    if (loading === request) loading = undefined;
  });
  return request;
}

/** The next useAccounts() asks the server again: for Settings as it opens
 * (an account may have been used since, #720) and each time it reads the
 * book again (useSettingsAccounts' `reload`), and for tests between cases. */
export function forgetAccounts(): void {
  loading = undefined;
}

export function useAccounts(): AccountsState {
  const [state, setState] = useState<AccountsState>({ failed: false });
  useEffect(() => {
    let live = true; // an unmounted screen sets no state
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
