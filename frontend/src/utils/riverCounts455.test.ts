import { describe, expect, it } from "vitest";
import { importRequestRows, toEditableRow } from "./riverImport";

function proposal(row_number: number, overrides: Partial<RiverProposal> = {}): RiverProposal {
  return {
    row_number,
    date: "2026-02-15T10:00:00Z",
    type: "Transfer",
    from_account: "Exchange BTC",
    to_account: "Wallet",
    amount: "0.00100000",
    type_choices: ["Transfer", "Withdrawal"],
    funding_choices: [],
    basis_autofilled: false,
    status: "new",
    ...overrides,
  };
}

describe("importRequestRows (#455)", () => {
  it("sends each row's file number, so an import error names the row the preview showed", () => {
    const unticked = { ...toEditableRow(proposal(2)), include: false };
    const found = toEditableRow(proposal(3, { status: "matched", matched_tx_id: 30 }));
    const ticked = toEditableRow(proposal(5));
    expect(importRequestRows([unticked, found, ticked]).map((r) => r.row_number)).toEqual([3, 5]);
  });
});
