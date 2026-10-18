// #449: a Purpose, a value or a Source chosen for a bitcoin account stays in
// the form (hidden, not cleared) when the account changes to a dollar one;
// the payload then sent it with the dollar withdrawal or deposit.
import { describe, expect, it } from "vitest";
import { buildTransactionPayload } from "./transactionForm";

// Runs with TZ=UTC (npm test), so datetime-local strings are UTC.
const form = (fields: Partial<TransactionFormData>) =>
  ({ timestamp: "2026-03-01T12:00", fee: 0, ...fields }) as TransactionFormData;

describe("a withdrawal's purpose and values go only with bitcoin leaving", () => {
  // Bitcoin Wallet, Gift, FMV 500, Spent's proceeds; then the account changed
  const leftOver = { type: "Withdrawal", purpose: "Gift", fmv_usd: 500, proceeds_usd: 500, amount: 100 } as const;

  it.each([
    ["Bank", "USD"],
    ["Exchange", "USD"],
  ] as const)("from %s (%s): no purpose, proceeds or FMV", (account, currency) => {
    const body = buildTransactionPayload(form({ ...leftOver, account, currency }));
    expect(body).toMatchObject({ purpose: "N/A", proceeds_usd: null, fmv_usd: null, broker_reporting: null });
  });

  it.each([
    ["Wallet", "BTC"],
    ["Exchange", "BTC"],
  ] as const)("from %s (%s): all of them, as typed", (account, currency) => {
    const body = buildTransactionPayload(form({ ...leftOver, account, currency, amount: 0.01 }));
    expect(body).toMatchObject({ purpose: "Gift", proceeds_usd: 500, fmv_usd: 500 });
  });
});

describe("a deposit's source goes only with bitcoin received", () => {
  it.each([
    ["Bank", "USD"],
    ["Exchange", "USD"],
  ] as const)("into %s (%s): no source", (account, currency) => {
    const body = buildTransactionPayload(form({ type: "Deposit", account, currency, amount: 100, source: "Income" }));
    expect(body).toMatchObject({ source: "N/A", cost_basis_usd: null });
  });

  it("into the Wallet: the source chosen", () => {
    const body = buildTransactionPayload(
      form({ type: "Deposit", account: "Wallet", currency: "BTC", amount: 0.01, source: "Income", costBasisUSD: 600 }),
    );
    expect(body).toMatchObject({ source: "Income", cost_basis_usd: 600 });
  });
});

describe("a dollar withdrawal's own label", () => {
  // Text an import or an older version saved, as listedPurpose passes it on
  const saved = (text: string) => text as WithdrawalPurpose;

  it("is sent back as it was (a purpose that isn't a bitcoin one, from an import)", () => {
    const body = buildTransactionPayload(
      form({ type: "Withdrawal", account: "Bank", currency: "USD", amount: 100, purpose: saved("Rent") }),
    );
    expect(body.purpose).toBe("Rent");
  });

  it("a bitcoin purpose saved on one by an older version is not", () => {
    const body = buildTransactionPayload(
      form({ type: "Withdrawal", account: "Bank", currency: "USD", amount: 100, purpose: saved(" gift ") }),
    );
    expect(body.purpose).toBe("N/A");
  });
});

describe("a dollar deposit's old free-text source", () => {
  it("is sent back as it was (text a version before 1.1.0 saved)", () => {
    const body = buildTransactionPayload(
      form({ type: "Deposit", account: "Bank", currency: "USD", amount: 100, source: "Salary" as DepositSource }),
    );
    expect(body.source).toBe("Salary");
  });
});
