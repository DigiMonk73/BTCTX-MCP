// A field-by-field refusal (FastAPI's 422, `detail` a list of input errors)
// is shown in its words, never as a list of objects (#448): a list given to
// a toast crashed the River import's preview (React error #31), and one put
// in a template string read "[object Object]".
import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";
import { saveFailedMessage } from "../components/transactionForm/saveTransaction";
import { detailOr, serverReason } from "./apiError";

function apiError(status: number, data: unknown): AxiosError {
  const config = { headers: new AxiosHeaders() };
  const response = { status, statusText: "", data, headers: {}, config } as AxiosResponse;
  return new AxiosError("Request failed with status code " + status, "ERR_BAD_REQUEST", config, null, response);
}

// What the server sends for River's "1,200" in a deposit's Cost Basis cell
const RIVER_COST_BASIS = apiError(422, {
  detail: [
    { type: "decimal_parsing", loc: ["body", "rows", 0, "cost_basis_usd"], msg: "Input should be a valid decimal", input: "1,200" },
  ],
});
// And for the form's Amount 12345678901
const FORM_AMOUNT = apiError(422, {
  detail: [{ type: "value_error", loc: ["body", "amount"], msg: "Value error, Amount is too large.", input: "12345678901" }],
});

describe("detailOr with a 422's list (#448)", () => {
  it("gives its words", () => {
    expect(detailOr(RIVER_COST_BASIS, "Import failed.")).toBe("Input should be a valid decimal");
    expect(detailOr(FORM_AMOUNT, "Import failed.")).toBe("Amount is too large.");
  });

  it("gives every field's words", () => {
    const err = apiError(422, {
      detail: [
        { loc: ["body", "rows", 0, "fee_amount"], msg: "Input should be a valid decimal" },
        { loc: ["body", "rows", 1, "amount"], msg: "Value error, BTC amount cannot exceed 8 decimal places" },
      ],
    });
    expect(detailOr(err, "Import failed.")).toBe(
      "Input should be a valid decimal BTC amount cannot exceed 8 decimal places",
    );
  });

  it("reads the same list outside axios", () => {
    const err = { response: { status: 422, data: { detail: [{ msg: "Value error, Amount is too large." }] } } };
    expect(detailOr(err, "Import failed.")).toBe("Amount is too large.");
  });

  it("is text even when the server's reason isn't", () => {
    expect(detailOr(apiError(422, { detail: [{ loc: ["body"] }] }), "Import failed.")).toBe("Import failed.");
    expect(detailOr(apiError(422, { detail: [] }), "Import failed.")).toBe("Import failed.");
    expect(detailOr(apiError(400, { detail: { why: "an object" } }), "Import failed.")).toBe("Import failed.");
    expect(detailOr(apiError(502, "<html>Bad gateway</html>"), "Import failed.")).toBe("Import failed.");
    expect(detailOr(apiError(400, null), "Import failed.")).toBe("Import failed.");
    expect(detailOr(null, "Import failed.")).toBe("Import failed.");
  });
});

describe("serverReason (#448)", () => {
  it("is the server's words, or null when it gave none", () => {
    expect(serverReason(apiError(409, { detail: "A later sell spends this buy's BTC." }))).toBe(
      "A later sell spends this buy's BTC.",
    );
    expect(serverReason(FORM_AMOUNT)).toBe("Amount is too large.");
    expect(serverReason(apiError(500, {}))).toBeNull();
    expect(serverReason(new Error("Network Error"))).toBeNull();
  });
});

describe("saveFailedMessage with a 422's list (#448)", () => {
  it("says the server's words, never [object Object]", () => {
    expect(saveFailedMessage(FORM_AMOUNT, "create")).toBe("Failed to create transaction: Amount is too large.");
    expect(saveFailedMessage(FORM_AMOUNT, "update")).toBe("Failed to update transaction: Amount is too large.");
  });

  it("keeps a reason given as text, and axios's own message without one", () => {
    expect(saveFailedMessage(apiError(400, { detail: "Insufficient BTC." }), "create")).toBe(
      "Failed to create transaction: Insufficient BTC.",
    );
    expect(saveFailedMessage(apiError(422, { detail: [{ loc: ["body"] }] }), "create")).toBe(
      "Failed to create transaction: Request failed with status code 422",
    );
  });
});
