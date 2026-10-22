// @vitest-environment jsdom
// B6b-10's proving test: the past-year warning's dialog (spec 5.8): the years
// and the server's sentence, what changes, the pending ones apart, why those
// couldn't be worked out, the box for adds, and its two buttons. Escape cancels,
// and the transaction panel's own Escape skips the key.
import "../test/setup";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PastYearsDialog from "./PastYearsDialog";
import type { PastYearsWarning } from "../utils/pastYears";

const DETAIL = "This changes the figures of tax years 2024 and 2025, which you may already have filed. " +
  "Confirm to save it: a copy of your ledger is made first.";
const ROW = { date: "2025-03-01 12:00", type: "Withdrawal", purpose: "Spent", amount: "0.50000000", unit: "BTC",
  accounts: ["Wallet"] };
const WARNING: PastYearsWarning = {
  detail: DETAIL, years: [2024, 2025], confirm: "fp-1", recalc_error: null,
  changes: [
    { ...ROW, id: 7, change: "Deleted.", years: [2025] },
    { ...ROW, id: 3, date: "2024-01-02 12:00", type: "Deposit", purpose: null, source: "MyBTC", amount: "1.00000000",
      change: "The lots it made would differ (their dates, BTC or cost); its totals stay the same.", years: [2024] },
  ],
  pending: [],
};
const SAVE = "Save anyway (a copy is made first)";

function show(warning: PastYearsWarning = WARNING, forAdd = false) {
  const onSave = vi.fn();
  const onCancel = vi.fn();
  render(<PastYearsDialog warning={warning} forAdd={forAdd} onSave={onSave} onCancel={onCancel} />);
  return { onSave, onCancel, user: userEvent.setup(), dialog: screen.getByRole("dialog") };
}

describe("PastYearsDialog", () => {
  it("is a modal dialog named for it, described by the server's sentence", () => {
    const { dialog } = show();
    expect(dialog).toHaveAccessibleName("Change an earlier tax year?");
    expect(dialog).toHaveAccessibleDescription(DETAIL);
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("lists what changes, row by row, as Ledger Review writes them", () => {
    show();
    const rows = within(screen.getByRole("list", { name: "What changes" })).getAllByRole("listitem");
    expect(rows.map((r) => r.textContent)).toEqual([
      "2025-03-01 12:00 · Withdrawal (Spent) · 0.50000000 BTC · Wallet: Deleted.",
      "2024-01-02 12:00 · Deposit (MyBTC) · 1.00000000 BTC · Wallet: The lots it made would differ (their dates, BTC or cost); its totals stay the same.",
    ]);
    expect(screen.queryByRole("list", { name: "These also change" })).toBeNull();
    expect(screen.queryByText(/Recalculate Ledger can't run now/)).toBeNull();
  });

  it("lists the pending ones apart, after their sentence", () => {
    show({ ...WARNING, changes: [], pending: [{ ...ROW, id: 9, change: "gain 9999.00 -> 10000.00.", years: [2025] }] });
    expect(screen.queryByRole("list", { name: "What changes" })).toBeNull();
    expect(screen.getByText("These also change, from rules fixed since they were saved:")).toBeInTheDocument();
    const pending = screen.getByRole("list", { name: "These also change" });
    expect(pending).toHaveTextContent("2025-03-01 12:00 · Withdrawal (Spent) · 0.50000000 BTC · Wallet: gain 9999.00 -> 10000.00.");
  });

  it("says why the pending ones couldn't be worked out", () => {
    show({ ...WARNING, recalc_error: "Ledger not balanced for BTC" });
    expect(screen.getByText("Recalculate Ledger can't run now: Ledger not balanced for BTC")).toBeInTheDocument();
  });

  it("Cancel comes first and has the focus; Save anyway and Cancel answer", async () => {
    const { onSave, onCancel, user } = show();
    const buttons = screen.getAllByRole("button");
    expect(buttons.map((b) => b.textContent)).toEqual(["Cancel", SAVE]);
    expect(buttons[0]).toHaveFocus();
    await user.click(screen.getByRole("button", { name: SAVE }));
    expect(onSave).toHaveBeenCalledWith(false);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("offers the box for adds only, and Save anyway says whether it was ticked", async () => {
    expect(show().dialog.querySelector("input")).toBeNull();
    document.body.innerHTML = "";
    const { onSave, user } = show(WARNING, true);
    const box = screen.getByRole("checkbox", {
      name: "Don't ask again for adds to 2024 and 2025 while this page is open" });
    expect(box).not.toBeChecked();
    await user.click(box);
    await user.click(screen.getByRole("button", { name: SAVE }));
    expect(onSave).toHaveBeenCalledWith(true);
  });

  it("Escape cancels, and the key is marked handled for the panel behind it", async () => {
    const seen: boolean[] = [];
    const panel = (e: KeyboardEvent) => seen.push(e.defaultPrevented);
    document.addEventListener("keydown", panel);
    const { onCancel, user } = show();
    await user.keyboard("{Escape}");
    document.removeEventListener("keydown", panel);
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(seen).toEqual([true]);
  });

  it("keeps Tab inside it", async () => {
    const { user } = show();
    await user.tab();
    expect(screen.getByRole("button", { name: SAVE })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  });
});
