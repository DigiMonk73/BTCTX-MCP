// The rest of the suite runs with TZ=UTC, where local time and UTC agree and
// a UTC/local mix-up can't show. These run as a US user (CDT, UTC-5 in summer).
process.env.TZ = "America/Chicago";

import { describe, expect, it } from "vitest";
import {
  buildTransactionPayload,
  mapTransactionToFormData,
  toDatetimeLocal,
} from "./transactionForm";

const sell = {
  id: 7,
  is_locked: false,
  type: "Sell",
  from_account_id: 4,
  to_account_id: 3,
  amount: 0.1,
  fee_amount: 130.16,
  fee_currency: "USD",
  gross_proceeds_usd: 13016.06,
  proceeds_usd: 12885.9,
  cost_basis_usd: 0,
  fmv_usd: 0,
  realized_gain_usd: 0,
} as unknown as ITransaction;

function editAndSave(timestamp: string): string {
  const form = mapTransactionToFormData({ ...sell, timestamp } as ITransaction);
  return buildTransactionPayload(form).timestamp as string;
}

describe("editing a transaction in a non-UTC timezone", () => {
  it("runs in Chicago time", () => {
    expect(new Date("2026-08-02T04:13:00Z").getHours()).toBe(23);
  });

  it("shows the stored time as local time", () => {
    const form = mapTransactionToFormData({ ...sell, timestamp: "2026-07-31T20:16:07Z" } as ITransaction);
    expect(form.timestamp).toBe("2026-07-31T15:16:07");
  });

  it("saves the time unchanged when only other fields were edited", () => {
    expect(editAndSave("2026-08-02T04:13:00Z")).toBe("2026-08-02T04:13:00.000Z");
  });

  it("keeps the seconds", () => {
    expect(editAndSave("2026-07-31T20:16:07Z")).toBe("2026-07-31T20:16:07.000Z");
  });

  it("keeps a winter (CST) time too", () => {
    expect(editAndSave("2026-01-15T03:30:00Z")).toBe("2026-01-15T03:30:00.000Z");
  });
});

describe("toDatetimeLocal", () => {
  it("gives a new transaction's default time in local time", () => {
    expect(toDatetimeLocal(new Date("2026-07-31T20:16:07Z"))).toBe("2026-07-31T15:16:07");
  });
});
