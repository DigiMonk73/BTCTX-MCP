// @vitest-environment jsdom
// B8-5f (spec 5.13): "Every item shows its amount in its account's currency …
// and names its account or accounts", by the server's `accounts` (B8-5): in the
// ordinary checks' lists and in the hourly check's.
import "../test/setup";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import LedgerReview from "../components/LedgerReview";
import type { LedgerReviewResponse, ReviewItem } from "../components/ledgerReview/types";
import { reviewAccounts } from "./transactionList";

describe("reviewAccounts", () => {
  it("names one account after the amount", () => {
    expect(reviewAccounts({ accounts: ["Credit Union"] })).toBe(" · Credit Union");
  });

  it("names a transfer's two, from then to", () => {
    expect(reviewAccounts({ accounts: ["Wallet", "Kraken BTC"] })).toBe(" · Wallet → Kraken BTC");
  });

  it("is blank when the server names none (an older server, or External only)", () => {
    expect(reviewAccounts({})).toBe("");
    expect(reviewAccounts({ accounts: [] })).toBe("");
  });
});

const item = (id: number, extra: Partial<ReviewItem>): ReviewItem => ({
  id, date: "2024-06-01 12:00", type: "Deposit", purpose: null, source: "MyBTC", amount: "0.25000000",
  unit: "BTC", issue: "No date originally acquired.", change: "", ...extra,
});

const REVIEW: LedgerReviewResponse = {
  timezone: "UTC", total: 2, reminders: 0, recalc_error: null,
  checks: [
    {
      key: "account_missing", kind: "check", title: "Accounts", action: "Fix it.", explanation: [], count: 1,
      items: [item(7, { type: "Transfer", source: null, amount: "200.00", unit: "USD", accounts: ["Bank", "Credit Union"] })],
    },
    {
      key: "day_priced_values", kind: "check", title: "Priced at the day", action: "", explanation: [], count: 1,
      items: [item(8, { year: 2024, accounts: ["Cold Storage"] })],
      years: [{ year: 2024, count: 1, listed: 1, ids: [8], income: "1.00", basis: "1.00", proceeds: "0.00",
        gift_values: "0.00", fees: "0.00" }],
    },
  ],
};

describe("Ledger Review's items name their accounts", () => {
  it("in an ordinary check's list and in the hourly check", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: REVIEW });
    render(<LedgerReview />);
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
    expect(screen.getByText(/#7 · .* · \$200\.00 · Bank → Credit Union —/)).toBeInTheDocument();
    expect(screen.getByText(/#8 · .* · 0\.25000000 BTC · Cold Storage —/)).toBeInTheDocument();
  });
});
