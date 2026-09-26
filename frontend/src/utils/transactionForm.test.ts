import { describe, expect, it } from "vitest";
import {
  buildTransactionPayload,
  localDatetimeToIso,
  mapTransactionToFormData,
} from "./transactionForm";

// Runs with TZ=UTC (npm test), so datetime-local strings are UTC.
const base = {
  id: 1,
  is_locked: false,
  timestamp: "2025-03-01T12:00:00Z",
  fee_amount: 0,
  cost_basis_usd: 0,
  proceeds_usd: 0,
  fmv_usd: 0,
  realized_gain_usd: 0,
} as unknown as ITransaction;

function tx(fields: Partial<ITransaction>): ITransaction {
  return { ...base, ...fields } as ITransaction;
}

/** Edit round trip: saved transaction -> form -> request body. */
function roundTrip(fields: Partial<ITransaction>) {
  return buildTransactionPayload(mapTransactionToFormData(tx(fields)));
}

describe("localDatetimeToIso", () => {
  it("turns a datetime-local value into ISO 8601", () => {
    expect(localDatetimeToIso("2025-03-01T12:00")).toBe("2025-03-01T12:00:00.000Z");
  });
});

describe("Sell", () => {
  const sell = {
    type: "Sell" as TransactionType,
    from_account_id: 4,
    to_account_id: 3,
    amount: 0.3,
    fee_amount: 10,
    fee_currency: "USD",
    gross_proceeds_usd: 20000,
    proceeds_usd: 19990,
  };

  it("edits the gross proceeds the user entered, not the stored net", () => {
    expect(mapTransactionToFormData(tx(sell)).grossProceedsUSD).toBe(20000);
    const body = roundTrip(sell);
    expect(body).toMatchObject({
      type: "Sell",
      from_account_id: 4,
      to_account_id: 3,
      amount: 0.3,
      fee_amount: 10,
      fee_currency: "USD",
      gross_proceeds_usd: 20000,
    });
    expect(body.proceeds_usd).toBeUndefined();
  });

  it("round-trips the 1099-DA override, and sends null for Automatic", () => {
    expect(roundTrip({ ...sell, broker_reporting: "basis" }).broker_reporting).toBe("basis");
    expect(roundTrip(sell).broker_reporting).toBeNull();
  });
});

describe("Withdrawal", () => {
  const spend = {
    type: "Withdrawal" as TransactionType,
    from_account_id: 2,
    to_account_id: 99,
    amount: 0.05,
    fee_amount: 0.0001,
    fee_currency: "BTC",
    purpose: "Spent",
    gross_proceeds_usd: 5000,
    proceeds_usd: 4995,
  };

  it("re-saving an edit sends the gross proceeds (no double fee)", () => {
    const form = mapTransactionToFormData(tx(spend));
    expect(form).toMatchObject({ account: "Wallet", currency: "BTC", purpose: "Spent" });
    expect(form.proceeds_usd).toBe(5000);
    expect(buildTransactionPayload(form)).toMatchObject({
      from_account_id: 2,
      to_account_id: 99,
      proceeds_usd: 5000,
      fee_currency: "BTC",
      purpose: "Spent",
    });
  });

  it("sends the override for a Spent withdrawal only", () => {
    expect(roundTrip({ ...spend, broker_reporting: "proceeds" }).broker_reporting).toBe("proceeds");
    expect(
      roundTrip({ ...spend, purpose: "Gift", broker_reporting: "proceeds" }).broker_reporting,
    ).toBeNull();
  });
});

describe("Transfer", () => {
  it("amount is what left the source; the form shows amount minus fee as received", () => {
    const transfer = {
      type: "Transfer" as TransactionType,
      from_account_id: 4,
      to_account_id: 2,
      amount: 0.5,
      fee_amount: 0.0001,
      fee_currency: "BTC",
    };
    const form = mapTransactionToFormData(tx(transfer));
    expect(form).toMatchObject({ fromAccount: "Exchange", toAccount: "Wallet", amountFrom: 0.5 });
    expect(form.amountTo).toBeCloseTo(0.4999, 8);
    expect(buildTransactionPayload(form)).toMatchObject({
      from_account_id: 4,
      to_account_id: 2,
      amount: 0.5,
      fee_amount: 0.0001,
      fee_currency: "BTC",
      broker_reporting: null,
    });
  });
});

describe("Buy and Deposit", () => {
  it("a Buy from the bank keeps its funding account and cost", () => {
    const body = roundTrip({
      type: "Buy",
      from_account_id: 1,
      to_account_id: 4,
      amount: 0.01,
      cost_basis_usd: 600,
      fee_amount: 2,
      fee_currency: "USD",
      broker_reporting: "basis", // not applicable to a Buy: never sent
    });
    expect(body).toMatchObject({
      from_account_id: 1,
      to_account_id: 4,
      amount: 0.01,
      cost_basis_usd: 600,
      fee_currency: "USD",
      broker_reporting: null,
    });
  });

  it("a BTC income deposit keeps its source and cost basis", () => {
    const body = roundTrip({
      type: "Deposit",
      from_account_id: 99,
      to_account_id: 2,
      amount: 0.002,
      cost_basis_usd: 120,
      fee_currency: "BTC",
      source: "Income",
    });
    expect(body).toMatchObject({
      from_account_id: 99,
      to_account_id: 2,
      amount: 0.002,
      cost_basis_usd: 120,
      source: "Income",
    });
  });
});

it("does not modify the form values it is given", () => {
  const form = mapTransactionToFormData(
    tx({ type: "Withdrawal", from_account_id: 2, to_account_id: 99, amount: 0.1, purpose: "Spent" }),
  );
  form.proceeds_usd = undefined;
  const snapshot = JSON.stringify(form);
  buildTransactionPayload(form);
  expect(JSON.stringify(form)).toBe(snapshot);
});

describe("blank means not given (F1)", () => {
  const form = (fields: Partial<TransactionFormData>) =>
    ({ timestamp: "2025-03-01T12:00", fee: 0, ...fields }) as TransactionFormData;

  it("a Spent withdrawal with blank proceeds sends null, not $0", () => {
    const body = buildTransactionPayload(
      form({ type: "Withdrawal", account: "Exchange", currency: "BTC", amount: 0.1, purpose: "Spent", proceeds_usd: NaN }),
    );
    expect(body.proceeds_usd).toBeNull();
    expect(body.fmv_usd).toBeNull();
  });

  it("a typed 0 stays 0", () => {
    const body = buildTransactionPayload(
      form({ type: "Withdrawal", account: "Exchange", currency: "BTC", amount: 0.1, purpose: "Spent", proceeds_usd: 0 }),
    );
    expect(body.proceeds_usd).toBe(0);
  });

  it("an income deposit with a blank basis sends null", () => {
    const body = buildTransactionPayload(
      form({ type: "Deposit", account: "Wallet", currency: "BTC", amount: 0.01, source: "Income", costBasisUSD: undefined }),
    );
    expect(body.cost_basis_usd).toBeNull();
  });

  it("types that don't take a basis send none", () => {
    const body = buildTransactionPayload(
      form({ type: "Transfer", fromAccount: "Wallet", fromCurrency: "BTC", toAccount: "Exchange", toCurrency: "BTC", amountFrom: 0.5 }),
    );
    expect(body.cost_basis_usd).toBeNull();
  });
});
