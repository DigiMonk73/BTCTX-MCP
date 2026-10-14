import { afterEach, describe, expect, it, vi } from "vitest";
import { historyPriceUrl } from "./converter";

describe("the converter's Date mode (#145, #260)", () => {
  afterEach(() => { vi.unstubAllEnvs(); });

  it("asks for the hour on this device's clock, or the day", () => {
    vi.stubEnv("TZ", "America/Chicago");
    expect(historyPriceUrl("2024-03-01", "9")).toBe("/bitcoin/price/history?at=2024-03-01T15%3A00%3A00.000Z");
    expect(historyPriceUrl("2024-03-01", "23")).toBe("/bitcoin/price/history?at=2024-03-02T05%3A00%3A00.000Z");
    expect(historyPriceUrl("2024-03-01", "")).toBe("/bitcoin/price/history?date=2024-03-01");
  });

  it("asks nothing for a date that names no moment", () => {
    expect(historyPriceUrl("20245-03-01", "9")).toBeNull(); // the date field takes a fifth digit
  });
});
