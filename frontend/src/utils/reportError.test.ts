import { describe, expect, it } from "vitest";
import { REPORT_FAILED, reportErrorMessage } from "./reportError";

const failed = (data: unknown) => ({ response: { status: 422, data } });

describe("reportErrorMessage", () => {
  it("reads the server's reason out of a Blob error body", async () => {
    const detail = "Withdrawal of 0.01 BTC on 2024-06-01: its network fee has no USD value.";
    const body = new Blob([JSON.stringify({ detail })], { type: "application/json" });
    expect(await reportErrorMessage(failed(body))).toBe(detail);
  });

  it("reads a string body too", async () => {
    expect(await reportErrorMessage(failed('{"detail": "No forms for 2023."}'))).toBe("No forms for 2023.");
  });

  it("falls back when there is no readable reason", async () => {
    expect(await reportErrorMessage(new Error("Network Error"))).toBe(REPORT_FAILED);
    expect(await reportErrorMessage(failed(new Blob(["<html>"])))).toBe(REPORT_FAILED);
    expect(await reportErrorMessage(failed({ detail: [{ msg: "x" }] }))).toBe(REPORT_FAILED);
    expect(await reportErrorMessage(null)).toBe(REPORT_FAILED);
  });
});
