// Longer, and a press long forgotten would move the keyboard out from under the user
const WAIT_MS = 5_000;

/**
 * Calls `then` with the page's element of that id: at once, or as soon as
 * it's added, if that's within `waitMs`. A link can be on screen before what
 * it goes to: the Dashboard's "Choose a source" before the price card, which
 * shows once its settings load (#612).
 */
export function whenShown(id: string, then: (element: HTMLElement) => void, waitMs = WAIT_MS): void {
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
    then(element);
  });
  const timer = window.setTimeout(() => observer.disconnect(), waitMs);
  observer.observe(document.body, { childList: true, subtree: true });
}
