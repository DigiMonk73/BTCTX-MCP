// A BTC withdrawal's purposes that aren't a sale: a gift, a donation, lost
// coins. They have no gain or loss of their own (the tax report says so);
// what they carry is their value, the fair market value (FMV).
const NOT_SOLD = ["gift", "donation", "lost"];

/** Gift, Donation or Lost, in any case (imports may write "gift"). */
export function isNotSold(purpose?: string | null): boolean {
  return NOT_SOLD.includes((purpose ?? "").toLowerCase());
}
