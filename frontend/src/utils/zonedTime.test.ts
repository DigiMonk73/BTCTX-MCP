import { describe, expect, it } from "vitest";
import { utcHourLabel, zonedHourToIso } from "./zonedTime";

describe("an hour in the tax timezone", () => {
  it("is the right UTC instant, winter and summer, east and west", () => {
    expect(zonedHourToIso("2024-03-01", 9, "America/Chicago")).toBe("2024-03-01T15:00:00.000Z");
    expect(zonedHourToIso("2024-07-01", 9, "America/Chicago")).toBe("2024-07-01T14:00:00.000Z");
    expect(zonedHourToIso("2024-03-01", 9, "Asia/Tokyo")).toBe("2024-03-01T00:00:00.000Z");
    expect(zonedHourToIso("2024-03-01", 0, "Asia/Tokyo")).toBe("2024-02-29T15:00:00.000Z");
    expect(zonedHourToIso("2024-03-01", 23, "UTC")).toBe("2024-03-01T23:00:00.000Z");
  });

  it("names its UTC hour", () => {
    expect(utcHourLabel("2024-03-01T15:00:00.000Z")).toBe("15:00 UTC");
  });
});
