// @vitest-environment jsdom
// B5b (#567), from its fresh review's second round: on the import's card, a
// preview is always the file on screen's, read the way the card now says.
import "../../test/setup";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import api from "../../api";
import { ToastProvider } from "../../contexts/ToastContext";
import RiverImport from "../RiverImport";

const PREVIEW = {
  success: true, total_rows: 1, new_count: 1, matched_count: 0, discrepancy_count: 0, errors: [], warnings: [],
  past_years_dated: [],
  proposals: [{
    row_number: 2, date: "2026-03-05T12:00:00Z", type: "Buy", from_account: "Exchange USD", to_account: "Exchange BTC",
    amount: "0.0003", cost_basis_usd: "25.00", type_choices: [], funding_choices: ["Bank", "Exchange USD"],
    basis_autofilled: false, status: "new",
  }],
};

function card() {
  vi.restoreAllMocks();
  vi.spyOn(api, "get").mockResolvedValue({ data: { mappings: [
    { id: "river", name: "River", ready_made: true, help: "", checked: true },
  ] } });
  vi.spyOn(api, "post").mockResolvedValue({ data: PREVIEW });
  render(<ToastProvider><RiverImport onPreviewShown={() => undefined} /></ToastProvider>);
  return userEvent.setup();
}

describe("the import's card", () => {
  it("drops a preview when another file is chosen: Import never sends the last file's rows", async () => {
    const user = card();
    await user.upload(screen.getByLabelText("River CSV file"), new File(["a"], "first.csv", { type: "text/csv" }));
    await user.click(screen.getByRole("button", { name: "Preview" }));
    expect(await screen.findByRole("button", { name: "Import 1 Transaction(s)" })).toBeTruthy();
    await user.upload(screen.getByLabelText("River CSV file"), new File(["b"], "second.csv", { type: "text/csv" }));
    expect(screen.queryByRole("button", { name: "Import 1 Transaction(s)" })).toBeNull();
  });
});
