import { describe, expect, it } from "vitest";
import { gainLabel, groupByDay, pageOf, sortTransactions } from "./transactionList";

const tx = (id: number, timestamp: string) => ({ id, timestamp }) as ITransaction;

describe("sortTransactions", () => {
  const list = [tx(1, "2024-03-01T12:00:00Z"), tx(3, "2024-01-01T12:00:00Z"), tx(2, "2024-02-01T12:00:00Z")];

  it("puts the latest date first", () => {
    expect(sortTransactions(list, "TIMESTAMP_DESC").map((t) => t.id)).toEqual([1, 2, 3]);
  });

  it("puts the last added first", () => {
    expect(sortTransactions(list, "CREATION_DESC").map((t) => t.id)).toEqual([3, 2, 1]);
  });

  it("leaves the list it was given as it was", () => {
    sortTransactions(list, "CREATION_DESC");
    expect(list.map((t) => t.id)).toEqual([1, 3, 2]);
  });
});

describe("pageOf", () => {
  const items = Array.from({ length: 23 }, (_, i) => i);

  it("slices the page asked for", () => {
    expect(pageOf(items, 2, 10)).toEqual({ page: 2, totalPages: 3, items: [10, 11, 12, 13, 14, 15, 16, 17, 18, 19] });
    expect(pageOf(items, 3, 10).items).toEqual([20, 21, 22]);
  });

  it("keeps the page between the first and the last", () => {
    expect(pageOf(items, 9, 10)).toMatchObject({ page: 3, items: [20, 21, 22] });
    expect(pageOf(items, 0, 10)).toMatchObject({ page: 1 });
  });

  it("shows page 1 of 0 with nothing to show", () => {
    expect(pageOf([], 4, 10)).toEqual({ page: 1, totalPages: 0, items: [] });
  });
});

describe("groupByDay", () => {
  it("groups by day in list order", () => {
    const groups = groupByDay([tx(1, "2024-06-02T12:00:00Z"), tx(2, "2024-06-02T11:00:00Z"), tx(3, "2024-06-01T12:00:00Z")]);
    expect(groups.map(([day, txs]) => [day, txs.map((t) => t.id)])).toEqual([
      ["Jun 2, 2024", [1, 2]],
      ["Jun 1, 2024", [3]],
    ]);
  });
});

describe("gainLabel", () => {
  const disposal = (type: string, purpose?: string) =>
    ({
      type,
      purpose,
      cost_basis_usd: 100,
      realized_gain_usd: 20,
      holding_period: "LONG",
    }) as ITransaction;

  it("shows a sell's and a spend's gain", () => {
    expect(gainLabel(disposal("Sell"))).toBe("Gain +$20.00 \u00b7 +20.00% \u00b7 Long-term");
    expect(gainLabel(disposal("Withdrawal", "Spent"))).toBe("Gain +$20.00 \u00b7 +20.00% \u00b7 Long-term");
  });

  it("shows none for a gift, a donation or lost coins: they aren't sales (#257)", () => {
    // As saved: a basis, and a gain of 0 ("Gain $0.00 · +0.00% · Long-term" before)
    for (const purpose of ["Gift", "Donation", "Lost", "gift"]) {
      expect(gainLabel({ ...disposal("Withdrawal", purpose), realized_gain_usd: 0 })).toBe("");
    }
  });

  it("shows none for a deposit, or with no basis and no gain", () => {
    expect(gainLabel(disposal("Deposit"))).toBe("");
    expect(gainLabel({ ...disposal("Sell"), cost_basis_usd: 0, realized_gain_usd: 0 })).toBe("");
  });
});
