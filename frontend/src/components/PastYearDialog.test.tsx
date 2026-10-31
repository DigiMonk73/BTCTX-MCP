// @vitest-environment jsdom
// The past-year question on its own (2.0 spec 5.8, #352): what it shows for
// an add, an edit and a delete, the keyboard (Cancel first, Escape taken
// before the panel's, Tab kept inside), and nothing to click while its
// request runs.
import "../test/setup";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import type { PastYearChange, PastYearKind, PastYearWarning } from "../utils/pastYears";
import PastYearDialog from "./PastYearDialog";

const item = (date: string, years: number[], change: string): PastYearChange => ({
  id: 3, date, type: "Withdrawal", purpose: "Spent", source: null, amount: "0.01", unit: "BTC",
  realized_gain_usd: "5.00", issue: "Changes with this save.", change, years,
});

const WARNING: PastYearWarning = {
  detail: "This changes the figures of tax years 2024 and 2025, which you may already have filed. " +
    "Confirm to save it: a copy of your ledger is made first.",
  years: [2024, 2025],
  changes: [item("2024-05-01 10:00", [2024], "gain 5.00 -> 6.00."), item("2025-02-01 10:00", [2025], "gain 1.00 -> 0.50.")],
  pending: [],
  recalc_error: null,
  exact: true,
  why_not_exact: null,
  timezone: "UTC",
  confirm: "f".repeat(64),
};

function renderDialog(kind: PastYearKind,
  extra: { busy?: boolean; warning?: PastYearWarning; changed?: "confirmed" | "quiet" } = {}) {
  const opener = createRef<HTMLElement>();
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  const props = { kind, warning: extra.warning ?? WARNING, busy: extra.busy ?? false, changed: extra.changed ?? null,
    opener, onConfirm, onCancel };
  const view = render(<PastYearDialog {...props} />);
  return { ...view, props, onConfirm, onCancel, user: userEvent.setup() };
}

describe("what it shows", () => {
  it("an add: the server's words, the changes under their years, and the box for its years", async () => {
    const { onConfirm, user } = renderDialog("add");
    const dialog = screen.getByRole("dialog", { name: "Change an earlier tax year?" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    expect(within(dialog).getByText(WARNING.detail)).toBeTruthy();
    expect(within(dialog).getByText("Tax year 2024")).toBeTruthy();
    expect(within(within(dialog).getByRole("list", { name: "Tax year 2025" })).getByRole("listitem").textContent)
      .toBe("2025-02-01 10:00 · Withdrawal (Spent) · 0.01 BTC — gain 1.00 -> 0.50.");
    await user.click(screen.getByRole("checkbox", { name: "Don't ask again for adds to 2024 and 2025 while this page is open" }));
    await user.click(screen.getByRole("button", { name: "Save anyway (a copy is made first)" }));
    expect(onConfirm).toHaveBeenCalledWith(true);
  });

  it("changes in one tax year have no heading", () => {
    renderDialog("add", { warning: { ...WARNING, years: [2024], changes: WARNING.changes.slice(0, 1) } });
    expect(screen.queryByText("Tax year 2024")).toBeNull();
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByRole("checkbox", { name: "Don't ask again for adds to 2024 while this page is open" })).toBeTruthy();
  });

  it("an edit: no box, and Save anyway confirms without keeping anything quiet", async () => {
    const { onConfirm, user } = renderDialog("edit");
    expect(screen.queryByRole("checkbox")).toBeNull();
    await user.click(screen.getByRole("button", { name: "Save anyway (a copy is made first)" }));
    expect(onConfirm).toHaveBeenCalledWith(false);
  });

  it("a delete: no box, and Delete anyway", async () => {
    const { onConfirm, user } = renderDialog("delete");
    expect(screen.queryByRole("checkbox")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save anyway (a copy is made first)" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Delete anyway (a copy is made first)" }));
    expect(onConfirm).toHaveBeenCalledWith(false);
  });

  it("a box left unticked keeps nothing quiet", async () => {
    const { onConfirm, user } = renderDialog("add");
    await user.click(screen.getByRole("button", { name: "Save anyway (a copy is made first)" }));
    expect(onConfirm).toHaveBeenCalledWith(false);
  });

  it("the date-based warning: why it isn't exact", () => {
    const why = "BitcoinTX couldn't work out exactly what changes quickly enough here, so it names every year this can reach.";
    renderDialog("edit", { warning: { ...WARNING, changes: [], exact: false, why_not_exact: why } });
    expect(screen.getByText(why)).toBeTruthy();
    expect(screen.queryAllByRole("listitem")).toEqual([]);
    expect(screen.queryByText(/^Dates in/)).toBeNull(); // no row, no date
  });

  // Its rows' dates are the server's, in the tax timezone (the one being
  // saved, for a timezone), not this device's clock as the form behind it (#737)
  it("names the zone its rows' dates are in, as Ledger Review does", () => {
    renderDialog("edit", { warning: { ...WARNING, timezone: "America/Chicago" } });
    expect(within(screen.getByRole("dialog")).getByText("Dates in America/Chicago.")).toBeTruthy();
  });

  it("and under rows that are only pending", () => {
    renderDialog("add", { warning: { ...WARNING, changes: [], pending: WARNING.changes } });
    expect(screen.getByText("Dates in UTC.")).toBeTruthy();
  });

  it("Recalculate Ledger's refusal shows under the pending changes, even with none listed", () => {
    renderDialog("add", { warning: { ...WARNING, recalc_error: "Row 9 spends more than it holds." } });
    const pending = screen.getByRole("group", { name: "These also change, from rules fixed since they were saved" });
    expect(within(pending).getByText("Recalculate Ledger can't run now: Row 9 spends more than it holds.")).toBeTruthy();
    expect(within(pending).queryAllByRole("listitem")).toEqual([]);
  });

  it("no pending changes: no such part", () => {
    renderDialog("add");
    expect(screen.queryByText(/These also change/)).toBeNull();
  });
});

describe("the keyboard and the busy state", () => {
  it("Cancel is focused first; Escape cancels, taken before the panel's own Escape", async () => {
    const { onCancel, user } = renderDialog("add");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
    let seenByPanel: boolean | null = null;
    const panel = (e: KeyboardEvent) => {
      seenByPanel = e.defaultPrevented;
    };
    document.addEventListener("keydown", panel);
    await user.keyboard("{Escape}");
    document.removeEventListener("keydown", panel);
    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(seenByPanel).toBe(true);
  });

  it("Tab stays inside", async () => {
    const { user } = renderDialog("edit");
    const save = screen.getByRole("button", { name: "Save anyway (a copy is made first)" });
    save.focus();
    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(save);
  });

  it("while its request runs: nothing to click, Escape does nothing, and it says what it's doing", async () => {
    const { onCancel, user } = renderDialog("add", { busy: true });
    for (const button of screen.getAllByRole("button")) expect((button as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toBe("Making a copy, then saving…");
    await user.keyboard("{Escape}");
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("while its request runs, it holds the focus itself: Tab can't leave it", async () => {
    const { props, rerender, user } = renderDialog("add");
    const outside = document.createElement("button");
    document.body.appendChild(outside);
    rerender(<PastYearDialog {...props} busy />);
    const dialog = screen.getByRole("dialog");
    expect(document.activeElement).toBe(dialog);
    await user.tab();
    expect(document.activeElement).toBe(dialog);
    outside.remove();
  });

  it("focused itself (a click on its text), Shift+Tab goes to its last button, never behind it", async () => {
    const { user } = renderDialog("edit");
    const outside = document.createElement("input");
    document.body.prepend(outside);
    screen.getByRole("dialog").focus();
    await user.tab({ shift: true });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Save anyway (a copy is made first)" }));
    outside.remove();
  });

  it("the page's own confirm of a quiet year refused: said why it asks", () => {
    renderDialog("add", { changed: "quiet" });
    expect(screen.getByRole("alert").textContent).toBe(
      "The ledger changed as this page confirmed it for you. Nothing was saved: check what this changes now.");
  });

  it("a delete's request says it deletes", () => {
    renderDialog("delete", { busy: true });
    expect(screen.getByRole("status").textContent).toBe("Making a copy, then deleting…");
  });

  it("a new warning after a confirm: said so, Cancel focused again, the box cleared", async () => {
    const { props, rerender, user } = renderDialog("add");
    await user.click(screen.getByRole("checkbox"));
    screen.getByRole("button", { name: "Save anyway (a copy is made first)" }).focus();
    const newer = { ...WARNING, years: [2025], confirm: "e".repeat(64) };
    rerender(<PastYearDialog {...props} warning={newer} changed="confirmed" />);
    expect(screen.getByRole("alert").textContent).toBe(
      "The ledger changed while this was open. Nothing was saved: check what this changes now.");
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Cancel" }));
    const box = screen.getByRole("checkbox", { name: "Don't ask again for adds to 2025 while this page is open" });
    expect((box as HTMLInputElement).checked).toBe(false);
  });

  it("focus goes back to what opened it when it closes", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    const view = render(
      <PastYearDialog kind="edit" warning={WARNING} busy={false} opener={{ current: opener }}
        onConfirm={() => undefined} onCancel={() => undefined} />,
    );
    expect(document.activeElement).not.toBe(opener);
    view.unmount();
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
