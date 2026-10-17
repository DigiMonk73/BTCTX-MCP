import { AxiosError, AxiosHeaders } from "axios";
import { describe, expect, it } from "vitest";
import { describeExtent, extentToConfirm } from "./deleteAll";

const failed = (status: number, data: unknown) =>
  new AxiosError("failed", "ERR", undefined, undefined, {
    status, data, statusText: "", headers: {}, config: { headers: new AxiosHeaders() },
  });

describe("describeExtent", () => {
  it("says how many and which tax years", () => {
    expect(describeExtent({ transactions: 118, first_year: 2023, last_year: 2026 })).toBe("118 transactions, 2023–2026");
    expect(describeExtent({ transactions: 1, first_year: 2024, last_year: 2024 })).toBe("1 transaction, 2024");
  });
});

describe("extentToConfirm", () => {
  it("reads what would go from the server's 409", () => {
    const what = { detail: "…", transactions: 2, first_year: 2024, last_year: 2025 };
    expect(extentToConfirm(failed(409, what))).toEqual({ transactions: 2, first_year: 2024, last_year: 2025 });
  });

  it("is null for any other failure", () => {
    expect(extentToConfirm(failed(403, { detail: "Wrong setup code." }))).toBeNull();
    expect(extentToConfirm(failed(409, { detail: "Something else." }))).toBeNull();
    expect(extentToConfirm(new Error("network"))).toBeNull();
  });
});
