import { describe, expect, it } from "vitest";
import { groupByDay, pageOf, sortTransactions } from "./transactionList";

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
