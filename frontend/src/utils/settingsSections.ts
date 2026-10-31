// Settings' sections (P7's mockups, #572; 2.0 spec 7.4, B7b): one open at a
// time, opened when asked, the open one remembered by this browser. A page
// with every section open was too busy (the owner, 2026-10-22).

/** The sections, in the page's order: "Wallets, exchanges and banks" after Account (5.9). */
export const SETTINGS_SECTIONS = [
  "account", "accounts", "review", "privacy", "ai", "data", "river", "backup", "about",
] as const;

export type SettingsSectionId = (typeof SETTINGS_SECTIONS)[number];

/** Where this browser keeps the open section (localStorage): its id, as JSON. */
export const OPEN_SECTION_KEY = "btctx:settings-open";

type Store = Pick<Storage, "getItem" | "setItem">;

function isSection(value: unknown): value is SettingsSectionId {
  return typeof value === "string" && (SETTINGS_SECTIONS as readonly string[]).includes(value);
}

/** The section this browser left open. None when nothing is stored, when
 * the storage can't be read (a private window, blocked site data) or when
 * what's stored isn't a section: the page then starts with all closed. */
export function rememberedOpen(store: Store | undefined): SettingsSectionId | null {
  try {
    const stored: unknown = JSON.parse(store?.getItem(OPEN_SECTION_KEY) ?? "null");
    return isSection(stored) ? stored : null;
  } catch {
    return null;
  }
}

/** Keep the open section for this browser. A storage that refuses (full,
 * blocked) only means it's forgotten: nothing else depends on it. */
export function rememberOpen(store: Store | undefined, open: SettingsSectionId | null): void {
  try {
    store?.setItem(OPEN_SECTION_KEY, JSON.stringify(open));
  } catch {
    // forgotten, as in a private window
  }
}

/** The section a link names after its "#" (/settings#privacy), or null. */
export function linkedSection(hash: string): SettingsSectionId | null {
  const id = hash.replace(/^#/, "");
  return isSection(id) ? id : null;
}

/** The open section after one's button is pressed: it opens, closing the one
 * before; or, when it was the open one, it closes. */
export function toggled(open: SettingsSectionId | null, id: SettingsSectionId): SettingsSectionId | null {
  return open === id ? null : id;
}

/** The open section as the page loads: the one a link names, else the remembered one. */
export function initiallyOpen(store: Store | undefined, hash: string): SettingsSectionId | null {
  return linkedSection(hash) ?? rememberedOpen(store);
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
 * shows whether something needs a look, a recalculation that would stop
 * included, which no count holds. */
export function reviewSummary(
  review: { total: number; reminders: number; recalc_error?: string | null } | null | undefined,
): string {
  if (review === undefined) return "Checking…";
  if (review === null) return "The review could not be loaded";
  const stops = Boolean(review.recalc_error);
  if (review.total === 0) {
    if (stops) return "Recalculate Ledger would stop: see why";
    return review.reminders > 0 ? "Nothing looks wrong" : "Nothing to review";
  }
  const toCheck = `${review.total} transaction${review.total === 1 ? "" : "s"} to check`;
  return stops ? `${toCheck}; Recalculate Ledger would stop` : toCheck;
}

/** Connect an AI Assistant's summary, by edition, as `aiSetup`'s `keyMode`
 * says (undefined: not known yet): the Mac app makes its own key, Docker and
 * StartOS have the owner create one (#724). Before the edition is known it
 * names no key, rather than one that may be wrong. Optional and off until
 * turned on, wherever it's introduced (the owner's decision 31). */
export function aiSummary(keyMode: boolean | undefined): string {
  const what = "Optional and off until you turn it on: an AI app that reads your ledger and enters transactions";
  if (keyMode === undefined) return what;
  return keyMode ? `${what}, with a key BitcoinTX keeps for it` : `${what}, with a key you create`;
}
