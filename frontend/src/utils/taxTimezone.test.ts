import { describe, expect, it } from "vitest";
import { timezoneSuggestion } from "./taxTimezone";

const NEVER_CHOSEN = { timezone: "UTC", source: "default" } as const;

describe("timezoneSuggestion (#334)", () => {
  it("suggests this computer's timezone while none was ever chosen, saying what saving does", () => {
    const line = timezoneSuggestion(NEVER_CHOSEN, "America/Chicago");
    expect(line).toContain("No tax timezone has been chosen, so tax dates use UTC.");
    expect(line).toContain("This computer is set to America/Chicago");
    expect(line).toContain("Saving recalculates the ledger");
    expect(line).toContain("also in years already filed");
  });

  it("says nothing once a timezone is chosen, or set by the server", () => {
    expect(timezoneSuggestion({ timezone: "UTC", source: "setting" }, "America/Chicago")).toBeNull();
    expect(timezoneSuggestion({ timezone: "Asia/Tokyo", source: "env" }, "America/Chicago")).toBeNull();
  });

  it("says nothing for a computer on UTC, or before the setting is read", () => {
    expect(timezoneSuggestion(NEVER_CHOSEN, "UTC")).toBeNull();
    expect(timezoneSuggestion(null, "America/Chicago")).toBeNull();
  });
});
