import { useState } from "react";
import { OPEN_LINES_KEY, openLinesAfter, readOpenLines, type BalanceLineKey } from "../../utils/dashboard";

// The browser may keep nothing (a private window, storage turned off): the
// lines then open closed each time, and nothing else changes
function storedOpenLines(): BalanceLineKey[] {
  try {
    return readOpenLines(window.localStorage.getItem(OPEN_LINES_KEY));
  } catch {
    return [];
  }
}

function storeOpenLines(open: BalanceLineKey[]): void {
  try {
    window.localStorage.setItem(OPEN_LINES_KEY, JSON.stringify(open));
  } catch {
    // Not kept: see storedOpenLines
  }
}

/** Portfolio Overview's open lines (#674), closed until opened and
 * remembered in this browser; and the toggle of one. */
export function useOpenLines(): [BalanceLineKey[], (key: BalanceLineKey) => void] {
  const [open, setOpen] = useState<BalanceLineKey[]>(storedOpenLines);
  const toggle = (key: BalanceLineKey) => {
    const next = openLinesAfter(open, key);
    setOpen(next);
    storeOpenLines(next);
  };
  return [open, toggle];
}
