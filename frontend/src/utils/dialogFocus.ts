// A modal dialog keeps the keyboard inside it (#256's review): Tab from the
// last control goes to the first, Shift+Tab from the first to the last.

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/** On Tab: wraps focus around `container`'s controls. */
export function keepFocusIn(container: HTMLElement | null, event: KeyboardEvent): void {
  if (!container || event.key !== "Tab") return;
  const items = Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE));
  if (items.length === 0) return;
  const first = items[0];
  const last = items[items.length - 1];
  const inside = container.contains(document.activeElement);
  if (event.shiftKey && (document.activeElement === first || !inside)) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && (document.activeElement === last || !inside)) {
    event.preventDefault();
    first.focus();
  }
}
