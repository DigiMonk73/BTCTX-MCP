import { describe, expect, it } from "vitest";
import {
  buildTransactionPayload,
  localDatetimeToIso,
  mapTransactionToFormData,
  plainBtcText,
} from "./transactionForm";
import { btcText } from "./format";
import { transferDestinations } from "./transferAccounts";
import { ONE_OF_EACH } from "../test/accountBooks";

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
  return buildTransactionPayload(mapTransactionToFormData(tx(fields), ONE_OF_EACH));
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
    expect(mapTransactionToFormData(tx(sell), ONE_OF_EACH).grossProceedsUSD).toBe(20000);
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
    const form = mapTransactionToFormData(tx(spend), ONE_OF_EACH);
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

  it("a gift saved without a value is edited blank, so saving fills it from the price (#255)", () => {
    const gift = { ...spend, purpose: "Gift", gross_proceeds_usd: undefined, proceeds_usd: undefined };
    const form = mapTransactionToFormData(tx({ ...gift, fmv_usd: undefined }), ONE_OF_EACH);
    expect(form.fmv_usd).toBeUndefined();
    expect(buildTransactionPayload(form).fmv_usd).toBeNull();
    // A value it has (typed, or from the price) is sent back as it is, with where it came from
    const priced = mapTransactionToFormData(tx({ ...gift, fmv_usd: 391.05, fmv_from_price: true }), ONE_OF_EACH);
    expect(priced).toMatchObject({ fmv_usd: 391.05, fmvFromPrice: true, fmvStored: 391.05 });
    expect(buildTransactionPayload(priced).fmv_usd).toBe(391.05);
    // A gift's $0 is a value it was given: sent back as $0
    expect(roundTrip({ ...gift, fmv_usd: 0 }).fmv_usd).toBe(0);
  });

  it("a sale's $0 value is edited blank, so making it a gift fills it from the price (#255)", () => {
    // Older forms saved $0 as every withdrawal's value; sent back, it would be a typed $0
    const form = mapTransactionToFormData(tx({ ...spend, fmv_usd: 0 }), ONE_OF_EACH);
    expect(form.fmv_usd).toBeUndefined();
    expect(buildTransactionPayload({ ...form, purpose: "Gift" }).fmv_usd).toBeNull();
  });

  it("sends the override for a Spent withdrawal only", () => {
    expect(roundTrip({ ...spend, broker_reporting: "proceeds" }).broker_reporting).toBe("proceeds");
    expect(
      roundTrip({ ...spend, purpose: "Gift", broker_reporting: "proceeds" }).broker_reporting,
    ).toBeNull();
  });

  it("reads a purpose an older version saved in another case as the listed one (#273)", () => {
    // "spent" showed a blank Purpose, and Update did nothing until one was picked
    const form = mapTransactionToFormData(tx({ ...spend, purpose: "spent", broker_reporting: "proceeds" }), ONE_OF_EACH);
    expect(form.purpose).toBe("Spent");
    expect(buildTransactionPayload(form)).toMatchObject({
      purpose: "Spent", proceeds_usd: 5000, broker_reporting: "proceeds",
    });
    for (const [saved, listed] of [["gift", "Gift"], ["DONATION", "Donation"], [" lost ", "Lost"], ["n/a", "N/A"]]) {
      expect(mapTransactionToFormData(tx({ ...spend, purpose: saved }), ONE_OF_EACH).purpose).toBe(listed);
    }
    // Text that isn't a listed purpose stays as saved
    expect(mapTransactionToFormData(tx({ ...spend, purpose: "Travel" }), ONE_OF_EACH).purpose).toBe("Travel");
    expect(mapTransactionToFormData(tx({ ...spend, purpose: undefined }), ONE_OF_EACH).purpose).toBe("N/A");
  });

  it("reads a gift's value the same way, spaces and all (#273's review)", () => {
    // " gift " opened as Gift with its typed $0 blank, so a save priced it
    const gift = { ...spend, purpose: " gift ", fmv_usd: 0, gross_proceeds_usd: undefined, proceeds_usd: undefined };
    const form = mapTransactionToFormData(tx(gift), ONE_OF_EACH);
    expect(form).toMatchObject({ purpose: "Gift", fmv_usd: 0 });
    expect(buildTransactionPayload(form).fmv_usd).toBe(0);
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
    const form = mapTransactionToFormData(tx(transfer), ONE_OF_EACH);
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
    const form = mapTransactionToFormData(tx(consolidation), ONE_OF_EACH);
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
    ONE_OF_EACH,
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
  it("an Inherited deposit's date of death comes back into the same field (#154)", () => {
    const form = mapTransactionToFormData(tx({
      type: "Deposit", from_account_id: 99, to_account_id: 4, amount: 0.02, cost_basis_usd: 2100,
      fee_currency: "BTC", source: "Inherited", acquired_at: "2026-02-01",
    }), ONE_OF_EACH);
    expect(form).toMatchObject({ source: "Inherited", acquiredDate: "2026-02-01", account: "Exchange" });
    // A row saved before 1.1.0 as free text "inherited" reads back as Inherited, and so does
    // every other source in another case (#273)
    for (const [saved, listed] of [["inherited", "Inherited"], ["income", "Income"], ["REBATE", "Rebate"],
      ["mybtc", "MyBTC"], [" interest ", "Interest"]]) {
      expect(mapTransactionToFormData(tx({ type: "Deposit", from_account_id: 99, to_account_id: 2, amount: 0.01,
        fee_currency: "BTC", source: saved }), ONE_OF_EACH).source).toBe(listed);
    }
    expect(buildTransactionPayload(form)).toMatchObject({ source: "Inherited", acquired_at: "2026-02-01" });
  });

  it("round-trips the date as the date stored, which no timezone moves (#185)", () => {
    // Read through a Date, "2021-03-14" is UTC midnight: March 13 in New York or Chicago
    const body = buildTransactionPayload(mapTransactionToFormData(tx({
      type: "Deposit", from_account_id: 99, to_account_id: 2, amount: 0.5, cost_basis_usd: 4000,
      fee_currency: "BTC", source: "MyBTC", acquired_at: "2021-03-14",
    }), ONE_OF_EACH));
    expect(body.acquired_at).toBe("2021-03-14");
  });

  it("is sent only for My BTC or Gift into a BTC account; otherwise null", () => {
    const deposit = (fields: Partial<TransactionFormData>) => buildTransactionPayload({
      type: "Deposit", timestamp: "2025-03-01T12:00", fee: 0, account: "Wallet", currency: "BTC", amount: 0.1,
      costBasisUSD: 10, acquiredDate: "2021-03-14", ...fields,
    } as TransactionFormData).acquired_at;
    expect(deposit({ source: "Gift" })).toBe("2021-03-14");
    expect(deposit({ source: "Inherited" })).toBe("2021-03-14"); // its date of death (#154)
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
    const form = mapTransactionToFormData(tx({ ...transfer, fee_usd: 7.77, fee_usd_manual: true }), ONE_OF_EACH);
    expect(form.feeUSD).toBe(7.77);
    expect(buildTransactionPayload(form).fee_usd).toBe(7.77);
  });

  it("clearing a typed value sends null (back to the price)", () => {
    const form = mapTransactionToFormData(tx({ ...transfer, fee_usd: 7.77, fee_usd_manual: true }), ONE_OF_EACH);
    form.feeUSD = NaN;
    expect(buildTransactionPayload(form).fee_usd).toBeNull();
  });

  it("USD fees never carry one", () => {
    const body = roundTrip({ type: "Transfer", from_account_id: 1, to_account_id: 3, amount: 100,
      fee_amount: 1, fee_currency: "USD" });
    expect("fee_usd" in body).toBe(false);
  });
});

describe("the stored values' price moment", () => {
  it("reaches the form, which says which price a stored fee value came from (#144)", () => {
    expect(mapTransactionToFormData(tx({ type: "Transfer", price_moment: "day" }), ONE_OF_EACH).priceMoment).toBe("day");
    expect(mapTransactionToFormData(tx({ type: "Transfer" }), ONE_OF_EACH).priceMoment).toBeNull();
  });
});

describe("a few sats shown as plain digits, never 5e-8 (#101)", () => {
  it("btcText writes a BTC amount to the satoshi, without trailing zeros", () => {
    expect([5e-8, 1.4e-7, 0.5, 1, 0, 0.00010005, 21000000].map(btcText))
      .toEqual(["0.00000005", "0.00000014", "0.5", "1", "0", "0.00010005", "21000000"]);
  });

  it("a 5-sat spend's amount and 3-sat fee start as plain digits when edited", () => {
    const form = mapTransactionToFormData(tx({ type: "Withdrawal", from_account_id: 2, to_account_id: 99,
      amount: 5e-8, fee_amount: 3e-8, fee_currency: "BTC", purpose: "Spent" }), ONE_OF_EACH);
    expect(plainBtcText(form)).toEqual([["amount", "0.00000005"], ["fee", "0.00000003"]]);
  });

  it("a transfer's amount received is to the satoshi, and its 14-sat fee plain digits", () => {
    const form = mapTransactionToFormData(tx({ type: "Transfer", from_account_id: 4, to_account_id: 2,
      amount: 0.1, fee_amount: 1.4e-7, fee_currency: "BTC" }), ONE_OF_EACH);
    expect(form.amountTo).toBe(0.09999986);
    expect(plainBtcText(form)).toEqual([["fee", "0.00000014"]]);
  });

  it("amounts a field shows as they are are left alone", () => {
    const form = mapTransactionToFormData(tx({ type: "Buy", from_account_id: 1, to_account_id: 4,
      amount: 0.000001, cost_basis_usd: 0.1, fee_amount: 0, fee_currency: "USD" }), ONE_OF_EACH);
    expect(plainBtcText(form)).toEqual([]);
  });

  it("the plain digits save as the same amounts", () => {
    const form = mapTransactionToFormData(tx({ type: "Withdrawal", from_account_id: 2, to_account_id: 99,
      amount: 5e-8, fee_amount: 3e-8, fee_currency: "BTC", purpose: "Spent", gross_proceeds_usd: 0.01 }), ONE_OF_EACH);
    for (const [name, text] of plainBtcText(form)) form[name] = text;
    const body = buildTransactionPayload(form);
    expect([body.amount, body.fee_amount]).toEqual([5e-8, 3e-8]);
  });
});
