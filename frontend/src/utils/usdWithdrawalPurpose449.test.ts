// #449: a Purpose, a value or a Source chosen for a bitcoin account stays in
// the form (hidden, not cleared) when the account changes to a dollar one;
// the payload then sent it with the dollar withdrawal or deposit.
import { describe, expect, it } from "vitest";
import { ONE_OF_EACH as book } from "../test/books";
import { buildTransactionPayload } from "./transactionForm";

// Runs with TZ=UTC (npm test), so datetime-local strings are UTC.
const form = (fields: Partial<TransactionFormData>) =>
  ({ timestamp: "2026-03-01T12:00", fee: 0, ...fields }) as TransactionFormData;

describe("a withdrawal's purpose and values go only with bitcoin leaving", () => {
  // Bitcoin Wallet, Gift, FMV 500, Spent's proceeds; then the account changed
  const leftOver = { type: "Withdrawal", purpose: "Gift", fmv_usd: 500, proceeds_usd: 500, amount: 100 } as const;

  it.each([
    ["Bank", 1],
    ["Exchange USD", 3],
  ] as const)("from %s (%s): no purpose, proceeds or FMV", (_name, fromAccountId) => {
    const body = buildTransactionPayload(form({ ...leftOver, fromAccountId }), book);
    expect(body).toMatchObject({ purpose: "N/A", proceeds_usd: null, fmv_usd: null, broker_reporting: null });
  });

  it.each([
    ["Wallet", 2],
    ["Exchange BTC", 4],
  ] as const)("from %s (%s): its purpose and FMV, as typed", (_name, fromAccountId) => {
    const body = buildTransactionPayload(form({ ...leftOver, fromAccountId, amount: 0.01 }), book);
    expect(body).toMatchObject({ purpose: "Gift", fmv_usd: 500 });
    // A gift has no proceeds: the Spent's typed before goes no further (#457)
    expect(body.proceeds_usd).toBeUndefined();
    expect(buildTransactionPayload(form({ ...leftOver, fromAccountId, purpose: "Spent" }), book).proceeds_usd).toBe(500);
  });
});

describe("a deposit's source goes only with bitcoin received", () => {
  it.each([
    ["Bank", 1],
    ["Exchange USD", 3],
  ] as const)("into %s (%s): no source", (_name, toAccountId) => {
    const body = buildTransactionPayload(form({ type: "Deposit", toAccountId, amount: 100, source: "Income" }), book);
    expect(body).toMatchObject({ source: "N/A", cost_basis_usd: null });
  });

  it("into the Wallet: the source chosen", () => {
    const body = buildTransactionPayload(
      form({ type: "Deposit", toAccountId: 2, amount: 0.01, source: "Income", costBasisUSD: 600 }), book,
    );
    expect(body).toMatchObject({ source: "Income", cost_basis_usd: 600 });
  });
});

describe("a dollar withdrawal's own label", () => {
  // Text an import or an older version saved, as listedPurpose passes it on
  const saved = (text: string) => text as WithdrawalPurpose;

  it("is sent back as it was (a purpose that isn't a bitcoin one, from an import)", () => {
    const body = buildTransactionPayload(
      form({ type: "Withdrawal", fromAccountId: 1, amount: 100, purpose: saved("Rent") }), book,
    );
    expect(body.purpose).toBe("Rent");
  });

  it("a bitcoin purpose saved on one by an older version is not", () => {
    const body = buildTransactionPayload(
      form({ type: "Withdrawal", fromAccountId: 1, amount: 100, purpose: saved(" gift ") }), book,
    );
    expect(body.purpose).toBe("N/A");
  });
});

describe("a dollar deposit's old free-text source", () => {
  it("is sent back as it was (text a version before 1.1.0 saved)", () => {
    const body = buildTransactionPayload(
      form({ type: "Deposit", toAccountId: 1, amount: 100, source: "Salary" as DepositSource }), book,
    );
    expect(body.source).toBe("Salary");
  });
});
