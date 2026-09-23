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

export async function setTaxTimezone(timezone: string): Promise<TaxTimezone> {
  const res = await api.put<TaxTimezone>("/settings/tax-timezone", { timezone });
  return res.data;
}

/**
 * First login: if no tax timezone was ever chosen (the server would use UTC),
 * adopt this browser's timezone. Returns the timezone it set, or null.
 */
export async function ensureTaxTimezone(): Promise<string | null> {
  try {
    const current = await getTaxTimezone();
    if (current.source !== "default") return null;
    const tz = browserTimezone();
    if (tz === "UTC") return null;
    await setTaxTimezone(tz);
    return tz;
  } catch {
    return null; // never block login on this
  }
}
