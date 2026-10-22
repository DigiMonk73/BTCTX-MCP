// The CSV export's file name is dated by this device's clock, as the screens
// show dates (#534): it took the UTC day, so an export at 9:37 pm on Oct 18
// in Chicago was named for Oct 19.
import { afterEach, describe, expect, it, vi } from "vitest";
import { csvExportName } from "./csvExport";

describe("csvExportName (#534)", () => {
  afterEach(() => { vi.unstubAllEnvs(); });

  it("names the day on this device's clock", () => {
    vi.stubEnv("TZ", "America/Chicago");
    expect(csvExportName(new Date("2026-10-19T02:37:00Z"))).toBe("btctx_transactions_2026-10-18.csv");
    vi.stubEnv("TZ", "Asia/Tokyo");
    expect(csvExportName(new Date("2026-10-18T20:00:00Z"))).toBe("btctx_transactions_2026-10-19.csv");
  });

  it("is the UTC day on a device set to UTC", () => {
    vi.stubEnv("TZ", "UTC");
    expect(csvExportName(new Date("2026-10-19T02:37:00Z"))).toBe("btctx_transactions_2026-10-19.csv");
  });
});
