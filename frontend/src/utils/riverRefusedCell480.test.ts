// #480: a cell River's Import sent and the server refused (FastAPI's 422,
// a typed Cost Basis of "1,200") was said with no row or column: "Input
// should be a valid decimal", twice over for two cells. The 422 places a
// cell by its index among the rows sent, not the file's row, so the message
// names the file's row the preview showed and the column it's in.
import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import { detailOr } from "./apiError";
import { importRequestRows, refusedCellPlace, toEditableRow } from "./riverImport";

function apiError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  const response = { status, statusText: "", data, headers: {}, config } as AxiosResponse;
  return new AxiosError("Request failed with status code " + status, "ERR_BAD_REQUEST", config, null, response);
}

function proposal(row_number: number, overrides: Partial<RiverProposal> = {}): RiverProposal {
  return {
    row_number,
    date: "2026-02-01T09:00:00Z",
    type: "Deposit",
    from_account: "External",
    to_account: "Exchange BTC",
    amount: "0.00002000",
    type_choices: ["Deposit"],
    funding_choices: [],
    basis_autofilled: false,
    status: "new",
    ...overrides,
  };
}

// Row 2 unticked (not sent), row 3 found in the ledger (sent first), row 5
// and row 6 ticked: the rows sent are the file's rows 3, 5 and 6
const SENT = importRequestRows([
  { ...toEditableRow(proposal(2)), include: false },
  toEditableRow(proposal(3, { status: "matched", matched_tx_id: 30 })),
  toEditableRow(proposal(5)),
  toEditableRow(proposal(6, { type: "Transfer", from_account: "Exchange BTC", to_account: "Wallet" })),
]);
const FALLBACK = "Import failed. No transactions were saved.";

describe("refusedCellPlace (#480)", () => {
  it("names the file's row and the column of each refused cell", () => {
    const err = apiError(422, {
      detail: [
        { type: "decimal_parsing", loc: ["body", "rows", 1, "cost_basis_usd"], msg: "Input should be a valid decimal", input: "1,200" },
        { type: "decimal_parsing", loc: ["body", "rows", 2, "fee_amount"], msg: "Input should be a valid decimal", input: "abc" },
      ],
    });
    expect(detailOr(err, FALLBACK, refusedCellPlace(SENT))).toBe(
      "Row 5 (Cost Basis): Input should be a valid decimal; Row 6 (Fee): Input should be a valid decimal",
    );
  });

  it("names the row alone for a field no column shows, and keeps pydantic's words", () => {
    const err = apiError(422, {
      detail: [{ loc: ["body", "rows", 0, "fee_currency"], msg: "Value error, Must be USD or BTC." }],
    });
    expect(detailOr(err, FALLBACK, refusedCellPlace(SENT))).toBe("Row 3: Must be USD or BTC.");
  });

  it("says only the words when the error isn't a row's", () => {
    const err = apiError(422, {
      detail: [
        { loc: ["body", "rows"], msg: "Field required" },
        { loc: ["body", "rows", 9, "amount"], msg: "Input should be a valid decimal" },
      ],
    });
    expect(detailOr(err, FALLBACK, refusedCellPlace(SENT))).toBe(
      "Field required; Input should be a valid decimal",
    );
  });

  it("leaves a refusal in words as it is", () => {
    const err = apiError(400, { detail: "Rows have errors: Row 5: Enter this deposit's cost basis." });
    expect(detailOr(err, FALLBACK, refusedCellPlace(SENT))).toBe(
      "Rows have errors: Row 5: Enter this deposit's cost basis.",
    );
    expect(detailOr(apiError(500, {}), FALLBACK, refusedCellPlace(SENT))).toBe(FALLBACK);
  });
});
