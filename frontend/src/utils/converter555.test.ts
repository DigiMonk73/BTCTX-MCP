import { describe, expect, it } from "vitest";
import { dayPriceNote } from "./converter";

describe("Date mode says when the day's price stands in for the hour (#555)", () => {
  it("names the day's price, in the transaction form's words, for an hour with none stored", () => {
    expect(dayPriceNote("15", "day")).toEqual({
      short: "The day's price (00:00 UTC)",
      full: "No price is stored for that hour, so this is the day's price (00:00 UTC).",
    });
    expect(dayPriceNote("0", "day")?.short).toBe("The day's price (00:00 UTC)");
  });

  it("says nothing for the hour's own price, or for the day asked for", () => {
    expect(dayPriceNote("15", "hour")).toBeNull();
    expect(dayPriceNote("", undefined)).toBeNull(); // Day: the server's answer names no moment
    expect(dayPriceNote("", "day")).toBeNull();
    expect(dayPriceNote("15", undefined)).toBeNull();
  });
});
