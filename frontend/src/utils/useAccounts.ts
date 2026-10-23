// The account book, loaded once per page (2.0 spec 5.4): every form and list
// on the page shares one GET /api/accounts/.
import { useCallback, useEffect, useState } from "react";
import api from "../api";

/** What a screen shows in place of its accounts when the book won't load. */
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
  // A rejection clears this request only while it is still the one stored:
  // forgetAccounts may have started a newer one, which stays
  request.catch(() => {
    if (loading === request) loading = undefined;
  });
  return request;
}

/** The next useAccounts() asks the server again: Settings calls it after
 * adding, hiding, showing or deleting an account. */
export function forgetAccounts(): void {
  loading = undefined;
}

/** The page's book; `reload` asks the server again after a change Settings made. */
export function useAccounts(): AccountsState & { reload: () => void } {
  const [state, setState] = useState<AccountsState>({ failed: false });
  const [asked, setAsked] = useState(0);
  useEffect(() => {
    // An unmounted screen sets no state
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
  }, [asked]);
  const reload = useCallback(() => {
    forgetAccounts();
    setAsked((n) => n + 1);
  }, []);
  return { ...state, reload };
}
