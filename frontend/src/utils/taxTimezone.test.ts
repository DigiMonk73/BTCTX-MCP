import { describe, expect, it } from "vitest";
import { canSaveTimezone, timezoneSuggestion } from "./taxTimezone";

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

describe("canSaveTimezone (#334)", () => {
  it("saves the timezone shown while none was ever chosen, so the suggestion can be ended", () => {
    expect(canSaveTimezone(NEVER_CHOSEN, "UTC")).toBe(true);
  });

  it("saves only another timezone once one is chosen or set by the server", () => {
    expect(canSaveTimezone({ timezone: "UTC", source: "setting" }, "UTC")).toBe(false);
    expect(canSaveTimezone({ timezone: "UTC", source: "setting" }, "Asia/Tokyo")).toBe(true);
    expect(canSaveTimezone({ timezone: "Asia/Tokyo", source: "env" }, "Asia/Tokyo")).toBe(false);
  });

  it("saves nothing before the setting is read, or with nothing selected", () => {
    expect(canSaveTimezone(null, "UTC")).toBe(false);
    expect(canSaveTimezone(NEVER_CHOSEN, "")).toBe(false);
  });
});
