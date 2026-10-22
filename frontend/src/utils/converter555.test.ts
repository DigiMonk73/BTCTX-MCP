import { describe, expect, it } from "vitest";
import { priceMomentLine } from "./converter";

describe("Date mode's line under the date and hour says which price shows (#555)", () => {
  it("names the UTC day of a day's price standing in for the hour, which can be another date", () => {
    // 23:00 on Mar 1 in Chicago is 05:00 UTC on Mar 2: Mar 2's price stands in
    expect(priceMomentLine("day", "2024-03-02T00:00:00Z")).toEqual({
      text: "Day's price: Mar 2, 00:00 UTC",
      why: "No price is stored for that hour.",
    });
    // 05:00 on Mar 1 in Tokyo is 20:00 UTC on Feb 29
    expect(priceMomentLine("day", "2024-02-29T00:00:00Z")?.text).toBe("Day's price: Feb 29, 00:00 UTC");
  });

  it("names the hour of an hour's own price, in UTC", () => {
    expect(priceMomentLine("hour", "2024-03-01T22:00:00Z")).toEqual({ text: "Hour's price: Mar 1, 22:00 UTC", why: null });
  });

  it("says nothing without an answer for a moment", () => {
    expect(priceMomentLine(undefined, undefined)).toBeNull(); // Day: the server's answer names no moment
    expect(priceMomentLine("day", undefined)).toBeNull();
    expect(priceMomentLine("week", "2024-03-01T00:00:00Z")).toBeNull();
  });
});
