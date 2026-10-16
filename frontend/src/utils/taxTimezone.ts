import api from "../api";

export interface TaxTimezone {
  timezone: string;
  source: "setting" | "env" | "default";
}

/** This computer's IANA timezone, e.g. "America/Chicago". */
export function browserTimezone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

export async function getTaxTimezone(): Promise<TaxTimezone> {
  const res = await api.get<TaxTimezone>("/settings/tax-timezone");
  return res.data;
}

/** Settings' Save: the owner's own choice (`chosen`, which a page from before #334 never sends). */
export async function setTaxTimezone(timezone: string): Promise<TaxTimezone> {
  const res = await api.put<TaxTimezone>("/settings/tax-timezone", { timezone, chosen: true });
  return res.data;
}

/** Whether Save can save `selected`: another timezone, or, while none was
 * ever chosen, any one, the one shown included, which ends Settings'
 * suggestion (#334). */
export function canSaveTimezone(current: TaxTimezone | null, selected: string): boolean {
  return Boolean(selected) && current !== null && (selected !== current.timezone || current.source === "default");
}

/**
 * At a login: if no tax timezone was ever chosen and the ledger is still
 * empty, the server saves this browser's timezone. With transactions it
 * changes nothing (#334): another timezone recalculates past years, so only
 * Settings changes it (`timezoneSuggestion`). A browser that reports UTC
 * fills nothing. Returns the timezone it set, or null.
 */
export async function ensureTaxTimezone(): Promise<string | null> {
  const tz = browserTimezone();
  if (tz === "UTC") return null;
  try {
    const res = await api.post<TaxTimezone & { filled: boolean }>("/settings/tax-timezone/fill", { timezone: tz });
    return res.data.filled ? tz : null;
  } catch {
    return null; // never block login on this
  }
}

/**
 * Settings' line while no tax timezone was ever chosen and this computer's
 * is another: what choosing it would do. Null otherwise.
 */
export function timezoneSuggestion(current: TaxTimezone | null, computer: string): string | null {
  if (current?.source !== "default" || computer === "UTC" || computer === current.timezone) return null;
  return (
    `No tax timezone has been chosen, so tax dates use ${current.timezone}. This computer is set to ` +
    `${computer}: if that's where you file, choose it and save. Saving recalculates the ledger, which ` +
    "can move a sale's tax year or term, also in years already filed."
  );
}
