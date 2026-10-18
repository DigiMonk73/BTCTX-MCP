// #476: a Sell saved before BitcoinTX kept a sale's gross (gross_proceeds_usd
// blank, proceeds_usd already net of its USD fee) opens in the edit form with
// the gross the server recovers for it, the net plus that fee
// (backend/services/transaction._sell_net_proceeds), so a save that changes
// nothing sends the gross back and takes no fee off again.
import { describe, expect, it } from "vitest";
import { buildTransactionPayload, mapTransactionToFormData } from "./transactionForm";
import { parseTransaction } from "./format";

/** A Sell as GET /api/transactions/{id} sends it: amounts as strings, a blank gross as null. */
const OLD_SELL = {
  id: 7,
  type: "Sell",
  timestamp: "2023-06-01T12:00:00Z",
  from_account_id: 4,
  to_account_id: 3,
  amount: "0.05000000",
  fee_amount: "10.00000000",
  fee_currency: "USD",
  cost_basis_usd: "1000.00",
  proceeds_usd: "4990.00",
  gross_proceeds_usd: null,
  realized_gain_usd: "3990.00",
} as unknown as ITransactionRaw;

/** What the edit form loads for a raw transaction (TransactionForm.tsx). */
function formFor(raw: Partial<Record<keyof ITransactionRaw, unknown>>) {
  return mapTransactionToFormData(parseTransaction({ ...OLD_SELL, ...raw } as ITransactionRaw));
}

describe("a Sell saved before its gross was kept (#476)", () => {
  it("opens with the net plus its USD fee as Gross Proceeds", () => {
    expect(formFor({}).grossProceedsUSD).toBe(5000);
  });

  it("saved unchanged, sends that gross and the same fee", () => {
    expect(buildTransactionPayload(formFor({}))).toMatchObject({
      type: "Sell",
      amount: 0.05,
      fee_amount: 10,
      fee_currency: "USD",
      gross_proceeds_usd: 5000,
    });
  });

  it("adds the fee to the cent", () => {
    expect(formFor({ proceeds_usd: "4990.07", fee_amount: "0.03" }).grossProceedsUSD).toBe(4990.1);
  });

  it("takes a missing fee currency as USD, as the server does for a Sell", () => {
    expect(formFor({ fee_currency: null }).grossProceedsUSD).toBe(5000);
  });

  it("adds no BTC fee: it never came out of the dollars", () => {
    expect(formFor({ fee_amount: "0.00010000", fee_currency: "BTC" }).grossProceedsUSD).toBe(4990);
  });

  it("with no fee, the net is the gross", () => {
    expect(formFor({ fee_amount: "0.00000000" }).grossProceedsUSD).toBe(4990);
  });

  it("with no proceeds stored either, shows none", () => {
    expect(formFor({ proceeds_usd: null }).grossProceedsUSD).toBe(0);
  });
});

describe("a Sell whose gross is kept", () => {
  it("opens with that gross, never the net plus the fee", () => {
    expect(formFor({ gross_proceeds_usd: "5000.00" }).grossProceedsUSD).toBe(5000);
    expect(formFor({ gross_proceeds_usd: "5003.00" }).grossProceedsUSD).toBe(5003);
  });

  it("saved unchanged, sends that gross", () => {
    expect(buildTransactionPayload(formFor({ gross_proceeds_usd: "5000.00" }))).toMatchObject({
      gross_proceeds_usd: 5000,
      fee_amount: 10,
    });
  });
});
