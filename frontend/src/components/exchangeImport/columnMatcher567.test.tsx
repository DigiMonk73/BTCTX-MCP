// @vitest-environment jsdom
// B5b (#567): the column matcher for another exchange's file. It shows each
// column the importer reads, the file's words for a kind of row with what
// each means, and how the file writes its times, dollars and numbers; it
// says what's still to match, and saves the mapping once it has a name.
import "../../test/setup";
import React, { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { emptyDraft, guessColumns, type Draft } from "../../utils/exchangeMapping";
import ColumnMatcher from "./ColumnMatcher";

const FILE: FileColumnsResponse = {
  header_row: 3,
  columns: ["When", "Type", "Coins", "Dollars", "State"],
  samples: [["2025-04-01 09:00", "Bought", "0.01", "1,010.00", "done"]],
  values: { When: ["2025-04-01 09:00"], Type: ["Bought", "Withdrew", "Card"], Coins: ["0.01"], Dollars: ["1,010.00"],
    State: ["done", "waiting"] },
  looks_like: null,
};

const Matcher: React.FC<{ start?: Draft; onSave?: (draft: Draft) => void; seen?: (draft: Draft) => void }> = (
  { start, onSave = () => {}, seen = () => {} },
) => {
  const [draft, setDraft] = useState<Draft>(start ?? { ...emptyDraft(), columns: guessColumns(FILE.columns) });
  return (
    <ColumnMatcher file={FILE} draft={draft} disabled={false} saving={false}
      onChange={(next) => { setDraft(next); seen(next); }} onSave={() => onSave(draft)} />
  );
};

describe("ColumnMatcher", () => {
  it("says what's still to match, and saves only once nothing is", () => {
    const save = vi.fn();
    render(<Matcher onSave={save} />);
    expect(screen.getByRole("status").textContent).toBe("Still to match: Date, Bitcoin amount.");
    fireEvent.change(screen.getByLabelText("Date"), { target: { value: "When" } });
    fireEvent.change(screen.getByLabelText("Bitcoin amount"), { target: { value: "Coins" } });
    expect(screen.getByRole("status").textContent).toBe("Still to match: What each kind of row is.");
    fireEvent.change(screen.getByLabelText("“Bought” is"), { target: { value: "buy" } });
    expect(screen.queryByRole("status")).toBeNull();
    const button = screen.getByRole("button", { name: "Save this mapping" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Mapping's name"), { target: { value: "Example Exchange" } });
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    expect(save).toHaveBeenCalledTimes(1);
  });

  it("lists the words of the kind column, each with what it means", () => {
    const seen = vi.fn();
    render(<Matcher seen={seen} />);
    expect(screen.getAllByRole("combobox").length).toBeGreaterThan(3);
    for (const word of ["Bought", "Withdrew", "Card"]) expect(screen.getByLabelText(`“${word}” is`)).toBeTruthy();
    fireEvent.change(screen.getByLabelText("“Withdrew” is"), { target: { value: "send" } });
    expect(seen.mock.lastCall?.[0].kinds).toEqual({ Withdrew: "send" });
  });

  it("asks which of the status column's words mean a completed row", () => {
    const seen = vi.fn();
    render(<Matcher seen={seen} />);
    fireEvent.change(screen.getByLabelText("Status (if any)"), { target: { value: "State" } });
    fireEvent.click(screen.getByLabelText("done"));
    expect(seen.mock.lastCall?.[0].done).toEqual(["done"]);
  });

  it("says how the file writes its dollars and times", () => {
    const seen = vi.fn();
    render(<Matcher seen={seen} />);
    fireEvent.click(screen.getByLabelText("A buy's dollars include its fee (the total paid)"));
    fireEvent.click(screen.getByLabelText("A sell's dollars are after its fee (what arrived)"));
    fireEvent.change(screen.getByLabelText("The file's times are in"), { target: { value: "America/Chicago" } });
    expect(seen.mock.lastCall?.[0]).toMatchObject({ buyAfterFee: true, sellAfterFee: true, zone: "America/Chicago" });
  });

  it("shows the file's first rows under its header", () => {
    render(<Matcher />);
    expect(screen.getByRole("table", { name: "The file's first rows" }).textContent).toContain("1,010.00");
  });
});
