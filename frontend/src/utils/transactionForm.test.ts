import { describe, expect, it } from "vitest";
import {
  buildTransactionPayload,
  dayIn,
  localDatetimeToIso,
  mapTransactionToFormData,
  transferDestinations,
} from "./transactionForm";

// Runs with TZ=UTC (npm test), so datetime-local strings are UTC.
const base = {
  id: 1,
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

describe("transferDestinations", () => {
  it("offers the other account of the currency first, and a BTC account itself (#159)", () => {
    expect(transferDestinations("Bank")).toEqual(["Exchange"]);
    expect(transferDestinations("Exchange", "USD")).toEqual(["Bank"]);
    expect(transferDestinations("Wallet")).toEqual(["Exchange", "Wallet"]);
    expect(transferDestinations("Exchange", "BTC")).toEqual(["Wallet", "Exchange"]);
    expect(transferDestinations("Exchange", undefined)).toEqual([]);
    expect(transferDestinations(undefined)).toEqual([]);
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

  it("a consolidation (#159) comes back as one: the same account, its fee, what arrived", () => {
    const consolidation = {
      type: "Transfer" as TransactionType,
      from_account_id: 2,
      to_account_id: 2,
      amount: 0.8,
      fee_amount: 0.0001,
      fee_currency: "BTC",
    };
    const form = mapTransactionToFormData(tx(consolidation));
    expect(form).toMatchObject({ fromAccount: "Wallet", toAccount: "Wallet", amountFrom: 0.8 });
    expect(form.amountTo).toBeCloseTo(0.7999, 8);
    expect(buildTransactionPayload(form)).toMatchObject({
      from_account_id: 2,
      to_account_id: 2,
      amount: 0.8,
      fee_amount: 0.0001,
      fee_currency: "BTC",
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

describe("a My BTC or Gift deposit's date originally acquired (#91)", () => {
  it("round-trips the date as a date alone (the server reads it as noon in the tax timezone)", () => {
    const body = buildTransactionPayload(mapTransactionToFormData(tx({
      type: "Deposit", from_account_id: 99, to_account_id: 2, amount: 0.5, cost_basis_usd: 4000,
      fee_currency: "BTC", source: "MyBTC", acquired_at: "2021-03-14T16:00:00Z", // noon in New York
    }), "America/New_York"));
    expect(body.acquired_at).toBe("2021-03-14");
  });

  it("shows the date as its day in the tax timezone, so a save doesn't move it", () => {
    const deposit = (acquired_at: string) => tx({
      type: "Deposit", from_account_id: 99, to_account_id: 2, amount: 0.5, cost_basis_usd: 4000,
      fee_currency: "BTC", source: "MyBTC", acquired_at,
    });
    // Noon on Jan 15 in Auckland's summer (UTC+13) is Jan 14 in UTC
    expect(mapTransactionToFormData(deposit("2023-01-14T23:00:00Z"), "Pacific/Auckland").acquiredDate).toBe("2023-01-15");
    // Stored at a 05:00 Tokyo deposit (the day's coins): March 31 in UTC, April 1 in Tokyo
    expect(mapTransactionToFormData(deposit("2025-03-31T20:00:00Z"), "Asia/Tokyo").acquiredDate).toBe("2025-04-01");
    expect(mapTransactionToFormData(deposit("2023-03-14T17:00:00Z"), "America/Chicago").acquiredDate).toBe("2023-03-14");
    expect(dayIn("2023-03-14T17:00:00Z", "Not/AZone")).toBe("2023-03-14");
  });

  it("is sent only for My BTC or Gift into a BTC account; otherwise null", () => {
    const deposit = (fields: Partial<TransactionFormData>) => buildTransactionPayload({
      type: "Deposit", timestamp: "2025-03-01T12:00", fee: 0, account: "Wallet", currency: "BTC", amount: 0.1,
      costBasisUSD: 10, acquiredDate: "2021-03-14", ...fields,
    } as TransactionFormData).acquired_at;
    expect(deposit({ source: "Gift" })).toBe("2021-03-14");
    expect(deposit({ source: "Income" })).toBeNull();
    expect(deposit({ source: "MyBTC", account: "Bank", currency: "USD" })).toBeNull();
    expect(deposit({ source: "MyBTC", acquiredDate: "" })).toBeNull();
  });
});

describe("a BTC fee's USD value (F14)", () => {
  const transfer = {
    type: "Transfer" as TransactionType,
    from_account_id: 4,
    to_account_id: 2,
    amount: 0.1,
    fee_amount: 0.0002,
    fee_currency: "BTC",
  };

  it("an edit that doesn't touch it leaves it out, so the stored value is kept", () => {
    const body = roundTrip({ ...transfer, fee_usd: 11.11, fee_usd_manual: false });
    expect("fee_usd" in body).toBe(false);
  });

  it("a typed value is sent and shown again when editing", () => {
    const form = mapTransactionToFormData(tx({ ...transfer, fee_usd: 7.77, fee_usd_manual: true }));
    expect(form.feeUSD).toBe(7.77);
    expect(buildTransactionPayload(form).fee_usd).toBe(7.77);
  });

  it("clearing a typed value sends null (back to the day's price)", () => {
    const form = mapTransactionToFormData(tx({ ...transfer, fee_usd: 7.77, fee_usd_manual: true }));
    form.feeUSD = NaN;
    expect(buildTransactionPayload(form).fee_usd).toBeNull();
  });

  it("USD fees never carry one", () => {
    const body = roundTrip({ type: "Transfer", from_account_id: 1, to_account_id: 3, amount: 100,
      fee_amount: 1, fee_currency: "USD" });
    expect("fee_usd" in body).toBe(false);
  });
});
