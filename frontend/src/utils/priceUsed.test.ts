import { describe, expect, it } from "vitest";
import { priceUsedWords, valueOrigin } from "./priceUsed";

const hour: PriceUsed = { at: "2024-03-01T14:00:00Z", moment: "hour", source: "bitstamp", usd_per_btc: "50083.00" };

describe("where a saved value came from (#145)", () => {
  it("names the hour or the day, and the source", () => {
    expect(priceUsedWords(hour)).toBe("$50,083.00 at 14:00 UTC, Mar 1, 2024 · Bitstamp");
    expect(priceUsedWords({ ...hour, moment: "day", at: "2024-03-01T00:00:00Z", source: "mempool" })).toBe(
      "$50,083.00, the day's price (00:00 UTC) on Mar 1, 2024 · your Mempool",
    );
    expect(priceUsedWords({ ...hour, source: "coinbase" })).toBe("$50,083.00 at 14:00 UTC, Mar 1, 2024 · Coinbase");
  });

  it("says From the price or Typed while the saved value shows, nothing otherwise", () => {
    expect(valueOrigin(true, 5008.3, 5008.3, hour)).toBe(
      "From the price: $50,083.00 at 14:00 UTC, Mar 1, 2024 · Bitstamp. Type a value to replace it.",
    );
    expect(valueOrigin(false, 7000, 7000, null)).toBe("Typed: you typed this value; it's kept as it is.");
    expect(valueOrigin(true, 5008.3, 5100, hour)).toBeNull(); // being changed
    expect(valueOrigin(undefined, undefined, 5008.3, hour)).toBeNull(); // a new transaction
    expect(valueOrigin(true, 5008.3, 5008.3, null)).toBe("From the price. Type a value to replace it.");
    // review of #190: a 0 or blank value isn't "typed": the save prices it
    expect(valueOrigin(false, 0, 0, null)).toBeNull();
  });
});
