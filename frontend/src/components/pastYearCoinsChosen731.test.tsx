// @vitest-environment jsdom
// The past-year question's line about a choice of coins (#711, 6.2): a
// write that adds or changes a choice on a transaction dated in an earlier
// tax year reads, as it's confirmed, that what counts is when the owner
// decided, not when it's typed here.
import "../test/setup";
import { render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";
import { pastYearWarning, type PastYearWarning } from "../utils/pastYears";
import PastYearDialog from "./PastYearDialog";

const LINE = "A choice of coins counts only if you made it by the time they left and your records show it.";
const WARNING: PastYearWarning = {
  detail: "This changes the figures of tax year 2025, which you may already have filed. Confirm to save it: a copy " +
    "of your ledger is made first.",
  years: [2025], changes: [], pending: [], recalc_error: null, exact: true, why_not_exact: null, timezone: "UTC",
  coins_chosen: LINE, confirm: "f".repeat(64),
};

const show = (warning: PastYearWarning) => render(<PastYearDialog kind="edit" warning={warning} busy={false}
  changed={null} opener={createRef<HTMLElement>()} onConfirm={vi.fn()} onCancel={vi.fn()} />);

describe("the past-year question and a choice of coins", () => {
  it("shows the server's line when the write chooses coins", () => {
    show(WARNING);
    expect(screen.getByText(LINE)).toBeTruthy();
  });

  it("shows none otherwise", () => {
    show({ ...WARNING, coins_chosen: null });
    expect(screen.queryByText(LINE)).toBeNull();
  });

  it("reads the line from the 409", () => {
    const err = Object.assign(new Error("409"), {
      isAxiosError: true, response: { status: 409, data: { ...WARNING } } });
    expect(pastYearWarning(err)?.coins_chosen).toBe(LINE);
    const without = Object.assign(new Error("409"), {
      isAxiosError: true, response: { status: 409, data: { ...WARNING, coins_chosen: undefined } } });
    expect(pastYearWarning(without)?.coins_chosen).toBeNull();
  });
});
