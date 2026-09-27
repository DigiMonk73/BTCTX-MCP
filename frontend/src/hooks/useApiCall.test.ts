import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import { extractErrorMessage } from "./useApiCall";

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
