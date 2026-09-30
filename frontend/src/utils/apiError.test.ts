import { describe, expect, it } from "vitest";
import { detailOr } from "./apiError";

describe("detailOr", () => {
  it("shows the server's reason", () => {
    const err = { response: { status: 422, data: { detail: "Row 3: unknown account." } } };
    expect(detailOr(err, "Import failed.")).toBe("Row 3: unknown account.");
  });

  it("falls back when the server gave none", () => {
    expect(detailOr({ response: { status: 500, data: {} } }, "Import failed.")).toBe("Import failed.");
    expect(detailOr({ response: { data: { detail: "" } } }, "Import failed.")).toBe("Import failed.");
    expect(detailOr(new Error("Network Error"), "Import failed.")).toBe("Import failed.");
  });
});
