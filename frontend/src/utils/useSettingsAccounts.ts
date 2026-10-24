// Settings changes the account book: it adds, hides, shows and deletes
// accounts (#355). Its book is the page's one (useAccounts) until it makes a
// change, then the book as the server has it after that change.
import { useCallback, useRef, useState } from "react";
import api from "../api";
import { forgetAccounts, useAccounts, type AccountsState } from "./useAccounts";

/** The book, and `reload`, which asks for it again and settles once it's there (or failed). */
export function useSettingsAccounts(): AccountsState & { reload: () => Promise<void> } {
  const page = useAccounts();
  const [changed, setChanged] = useState<AccountsState>();
  const asked = useRef(0);
  const reload = useCallback(() => {
    // A screen opened later asks again too, and sees the change
    forgetAccounts();
    // Two changes in a row: only the last answer counts, whichever comes first
    const ask = ++asked.current;
    return api.get<AccountBook>("/accounts/").then(
      (res) => {
        if (ask === asked.current) setChanged({ book: res.data, failed: false });
      },
      () => {
        if (ask === asked.current) setChanged({ failed: true });
      },
    );
  }, []);
  return { ...(changed ?? page), reload };
}
