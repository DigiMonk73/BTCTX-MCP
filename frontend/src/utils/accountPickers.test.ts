// B6a-2 and B6a-3: which accounts each picker offers (spec 5.5, 5.13), from the
// book: hidden accounts only when they're the row's own, never a fee account.
import { describe, expect, it } from "vitest";
import { MISSING, ONE_OF_EACH as ONE, TWO_OF_EACH as TWO } from "../test/accountBooks";
import { transferTargets, visibleAccounts } from "./accounts";

describe("visible", () => {
  it("is the owner's accounts not hidden, in the book's order", () => {
    expect(visibleAccounts(TWO)).toEqual([1, 100, 2, 101, 3, 4, 102, 103]);
  });

  it("adds the row's own hidden account, never a fee account or a missing one", () => {
    expect(visibleAccounts(TWO, 104)).toEqual([1, 100, 2, 101, 104, 3, 4, 102, 103]);
    expect(visibleAccounts(TWO, 5)).toEqual([1, 100, 2, 101, 3, 4, 102, 103]);
    expect(visibleAccounts(TWO, MISSING)).toEqual([1, 100, 2, 101, 3, 4, 102, 103]);
  });
});

describe("transfer", () => {
  it("goes to accounts of the same currency; a dollar account never to itself", () => {
    expect(transferTargets(TWO, 1)).toEqual([100, 3, 102]);
    expect(transferTargets(TWO, 3)).toEqual([1, 100, 102]);
  });

  it("offers a bitcoin account itself (a consolidation, #159)", () => {
    expect(transferTargets(TWO, 2)).toEqual([2, 101, 4, 103]);
    expect(transferTargets(TWO, 103)).toEqual([2, 101, 4, 103]);
  });

  it("shows a hidden target only when it's the row's own", () => {
    expect(transferTargets(TWO, 2, 104)).toEqual([2, 101, 104, 4, 103]);
  });

  it("keeps 1.x's choices with one of each", () => {
    expect(transferTargets(ONE, 1)).toEqual([3]);
    expect(transferTargets(ONE, 3)).toEqual([1]);
    expect(transferTargets(ONE, 2)).toEqual([2, 4]);
    expect(transferTargets(ONE, 4)).toEqual([2, 4]);
  });

  it.each([99, MISSING, undefined, 5])("offers nothing from %s, which isn't one of yours", (from) => {
    expect(transferTargets(TWO, from)).toEqual([]);
  });
});
