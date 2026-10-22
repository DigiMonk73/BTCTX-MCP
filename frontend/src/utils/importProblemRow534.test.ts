// #534 ("Row 0:"): an import preview said an error about the whole file as
// if it were a row's, "Row 0: This does not look like a River
// bitcoin-activity CSV. Missing columns: …". The server numbers such an
// error 0; the preview says it alone, and a row's error under its row.
import { describe, expect, it } from "vitest";
import { problemText } from "./importProblem";

describe("problemText (#534)", () => {
  it("says an error about the whole file without a row", () => {
    expect(problemText({
      row_number: 0,
      message: "This does not look like a River bitcoin-activity CSV. Missing columns: fee amount",
    })).toBe("This does not look like a River bitcoin-activity CSV. Missing columns: fee amount");
    expect(problemText({ row_number: 0, message: "No valid transactions found in file." }, undefined)).toBe(
      "No valid transactions found in file.",
    );
  });

  it("says a row's error under its row, and its column when given one", () => {
    const problem = { row_number: 4, message: "Amount must be positive." };
    expect(problemText(problem)).toBe("Row 4: Amount must be positive.");
    expect(problemText(problem, "amount")).toBe("Row 4 (amount): Amount must be positive.");
    expect(problemText(problem, null)).toBe("Row 4: Amount must be positive.");
  });
});
