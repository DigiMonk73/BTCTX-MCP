// Settings changes the account book: it adds, hides, shows and deletes
// accounts (#355). Its book is read afresh as it opens, then, after each
// change it makes, the book as the server has it after that change.
import { useCallback, useLayoutEffect, useRef, useState } from "react";
import api from "../api";
import { forgetAccounts, useAccounts, type AccountsState } from "./useAccounts";

/** The book, and `reload`, which asks for it again and settles once it's there (or failed). */
export function useSettingsAccounts(): AccountsState & { reload: () => Promise<void> } {
  // Settings offers Delete by `in_use`, and an account may have been used since
  // the page read the book (a deposit on the Transactions page, the AI
  // connector, #720): the page's book is asked for again as Settings opens.
  // A layout effect runs before useAccounts' effect asks, so that ask is the
  // fresh one, and any screen opening with Settings shares it.
  useLayoutEffect(() => forgetAccounts(), []);
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
