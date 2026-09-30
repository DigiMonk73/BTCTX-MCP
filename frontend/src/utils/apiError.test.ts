import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import { detailOr, extractErrorMessage } from "./apiError";

function apiError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  const response = { status, statusText: "", data, headers: {}, config } as AxiosResponse;
  return new AxiosError("Request failed", "ERR_BAD_REQUEST", config, null, response);
}

describe("extractErrorMessage", () => {
  it("shows the server's message", () => {
    expect(extractErrorMessage(apiError(403, { detail: "Current password is incorrect." }))).toBe(
      "Current password is incorrect.",
    );
  });

  it("shows input errors (422) as text, not a list of objects", () => {
    const err = apiError(422, {
      detail: [{ loc: ["body", "password"], msg: "Value error, The password must be at least 12 characters." }],
    });
    expect(extractErrorMessage(err)).toBe("The password must be at least 12 characters.");
  });

  it("falls back to the status", () => {
    expect(extractErrorMessage(apiError(403, {}))).toBe("Access denied.");
  });
});

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
