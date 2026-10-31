// Longer, and a press long forgotten would move the keyboard out from under the user
const WAIT_MS = 5_000;

/**
 * Calls `then` with the page's element of that id: at once, or as soon as
 * it's added, if that's within `waitMs` and the user hasn't moved on since
 * pressing `from`. A link can be on screen before what it goes to: the
 * Dashboard's "Choose a source" before the price card, which shows once its
 * settings load (#612).
 */
export function whenShown(
  id: string,
  from: HTMLElement,
  then: (element: HTMLElement) => void,
  waitMs = WAIT_MS,
): void {
  const now = document.getElementById(id);
  if (now) {
    then(now);
    return;
  }
  const observer = new MutationObserver(() => {
    const element = document.getElementById(id);
    if (!element) return;
    observer.disconnect();
    window.clearTimeout(timer);
    if (stillWanted(from)) then(element);
  });
  const timer = window.setTimeout(() => observer.disconnect(), waitMs);
  observer.observe(document.body, { childList: true, subtree: true });
}

/** What was pressed is still on the page, and the keyboard on it or on nothing:
 *  not gone to another page (Settings has its own price card) or another control. */
function stillWanted(from: HTMLElement): boolean {
  const active = document.activeElement;
  return from.isConnected && (active === from || active === null || active === document.body);
}
