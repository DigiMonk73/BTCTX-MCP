// A deposit's sources and a withdrawal's purposes: which purposes aren't a
// sale, the form's lists, and a saved one in its listed spelling.

// A BTC withdrawal's purposes that aren't a sale: a gift, a donation, lost
// coins. They have no gain or loss of their own (the tax report says so);
// what they carry is their value, the fair market value (FMV).
const NOT_SOLD = ["gift", "donation", "lost"];

/** Gift, Donation or Lost, in any case and spacing (imports may write "gift"). */
export function isNotSold(purpose?: string | null): boolean {
  return NOT_SOLD.includes((purpose ?? "").trim().toLowerCase());
}

/** Spent, Gift, Donation or Lost, in any case and spacing: what only
 * bitcoin leaving can be (#449). */
export function isBtcPurpose(purpose?: string | null): boolean {
  return isNotSold(purpose) || (purpose ?? "").trim().toLowerCase() === "spent";
}

// The form's choices, "N/A" (none) included. The River import offers its
// own lists (utils/riverImport.ts), without "N/A".
const FORM_SOURCES: DepositSource[] = ["N/A", "MyBTC", "Gift", "Inherited", "Income", "Interest", "Reward", "Rebate"];
const FORM_PURPOSES: WithdrawalPurpose[] = ["N/A", "Spent", "Gift", "Donation", "Lost"];

/** A saved value in its listed spelling, matched ignoring case and spaces
 * as the server reads it: a row saved by an older version may say
 * "inherited" (#154) or "spent" (#273). Other text stays as saved; none is
 * "N/A". */
function listed<T extends string>(choices: T[], saved: string | null | undefined): T {
  const wanted = (saved ?? "N/A").trim().toLowerCase();
  return choices.find((c) => c.toLowerCase() === wanted) ?? (saved as T);
}

/** A deposit's saved source in its listed spelling ("income" is Income). */
export function listedSource(saved: string | null | undefined): DepositSource {
  return listed(FORM_SOURCES, saved);
}

/** A withdrawal's saved purpose in its listed spelling ("spent" is Spent). */
export function listedPurpose(saved: string | null | undefined): WithdrawalPurpose {
  return listed(FORM_PURPOSES, saved);
}
