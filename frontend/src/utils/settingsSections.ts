// Settings' sections (P7's mockups, #572; 2.0 spec 7.4, B7b): each opens when
// asked, and the open ones are remembered by this browser. A page with every
// section open was too busy (the owner, 2026-10-22).

/** The sections, in the page's order: "Wallets, exchanges and banks" after Account (5.9). */
export const SETTINGS_SECTIONS = [
  "account", "accounts", "review", "privacy", "ai", "data", "river", "backup", "about",
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number];

/** Where this browser keeps the open sections (localStorage): a JSON list of ids. */
export const OPEN_SECTIONS_KEY = "btctx:settings-open";

type Store = Pick<Storage, "getItem" | "setItem">;

function isSection(value: unknown): value is SettingsSectionId {
  return typeof value === "string" && (SETTINGS_SECTIONS as readonly string[]).includes(value);
}

/** The sections this browser left open. None when nothing is stored, when the
 * storage can't be read (a private window, blocked site data) or when what's
 * stored isn't a list: the page then starts with every section closed. */
export function rememberedOpen(store: Store | undefined): SettingsSectionId[] {
  try {
    const stored: unknown = JSON.parse(store?.getItem(OPEN_SECTIONS_KEY) ?? "[]");
    return Array.isArray(stored) ? SETTINGS_SECTIONS.filter((id) => stored.includes(id)) : [];
  } catch {
    return [];
  }
}

/** Keep the open sections for this browser. A storage that refuses (full,
 * blocked) only means they're forgotten: nothing else depends on them. */
export function rememberOpen(store: Store | undefined, open: readonly SettingsSectionId[]): void {
  try {
    store?.setItem(OPEN_SECTIONS_KEY, JSON.stringify(open));
  } catch {
    // forgotten, as in a private window
  }
}

/** The section a link names after its "#" (/settings#privacy), or null. */
export function linkedSection(hash: string): SettingsSectionId | null {
  const id = hash.replace(/^#/, "");
  return isSection(id) ? id : null;
}

/** The open sections after one is opened or closed, in the page's order. */
export function toggled(open: readonly SettingsSectionId[], id: SettingsSectionId): SettingsSectionId[] {
  return SETTINGS_SECTIONS.filter((s) => (s === id ? !open.includes(s) : open.includes(s)));
}

/** The open sections as the page loads: the remembered ones, and the one a link names. */
export function initiallyOpen(store: Store | undefined, hash: string): SettingsSectionId[] {
  const open = rememberedOpen(store);
  const linked = linkedSection(hash);
  return linked && !open.includes(linked) ? toggled(open, linked) : open;
}

/** This browser's localStorage, or undefined where reading it throws (blocked site data). */
export function browserStore(): Store | undefined {
  try {
    return window.localStorage;
  } catch {
    return undefined;
  }
}

/** Ledger Review's summary, from its last answer (undefined: not yet; null:
 * it failed), as the section's own text says it: a closed section still
 * shows whether something needs a look. */
export function reviewSummary(review: { total: number; reminders: number } | null | undefined): string {
  if (review === undefined) return "Checking…";
  if (review === null) return "The review could not be loaded";
  if (review.total === 0) return review.reminders > 0 ? "Nothing looks wrong" : "Nothing to review";
  return `${review.total} transaction${review.total === 1 ? "" : "s"} to check`;
}
