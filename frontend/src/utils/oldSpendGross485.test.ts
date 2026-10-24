// #485: a BTC withdrawal saved before BitcoinTX kept a withdrawal's gross
// (gross_proceeds_usd blank, proceeds_usd the net that version stored) opens
// in the edit form with the gross the server recovers for it
// (backend/services/transaction._withdrawal_gross_proceeds), so a save that
// changes nothing keeps its proceeds. It opened with $0, and the save made a
// Spent a $0 sale.
import { describe, expect, it } from "vitest";
import { ONE_OF_EACH as book } from "../test/books";
import { buildTransactionPayload, mapTransactionToFormData } from "./transactionForm";
import { parseTransaction } from "./format";

/** A Spent as GET /api/transactions/{id} sends it: amounts as strings, a blank gross as null. */
const OLD_SPEND = {
  id: 9,
  type: "Withdrawal",
  timestamp: "2024-06-01T00:00:00Z",
  from_account_id: 4,
  to_account_id: 99,
  amount: "0.01000000",
  fee_amount: "0.00010000",
  fee_currency: "BTC",
  purpose: "Spent",
  cost_basis_usd: "200.00",
  proceeds_usd: "990.10",
  gross_proceeds_usd: null,
  realized_gain_usd: "790.10",
  fee_usd: "10.00",
  fee_usd_manual: false,
} as unknown as ITransactionRaw;

/** What the edit form loads for a raw transaction (TransactionForm.tsx). */
function formFor(raw: Partial<Record<keyof ITransactionRaw, unknown>>) {
  return mapTransactionToFormData(parseTransaction({ ...OLD_SPEND, ...raw } as ITransactionRaw), book);
}

describe("a Spent saved before its gross was kept (#485)", () => {
  it("opens with the gross the server recovers: the stored net with its BTC fee's offset undone", () => {
    // 990.10 x (0.01 + 0.0001) / 0.01
    expect(formFor({}).proceeds_usd).toBe(1000);
  });

  it("saved unchanged, sends that gross, which says it was typed", () => {
    const form = formFor({});
    expect(form.proceedsStored).toBe(1000);
    expect(buildTransactionPayload(form, book)).toMatchObject({ purpose: "Spent", proceeds_usd: 1000 });
  });

  it("with no BTC fee, the stored proceeds are the gross", () => {
    expect(formFor({ fee_amount: "0.00000000" }).proceeds_usd).toBe(990.1);
  });

  it("with a gross kept, opens with it", () => {
    expect(formFor({ gross_proceeds_usd: "1000.00", proceeds_usd: "990.00" }).proceeds_usd).toBe(1000);
  });

  it("a typed $0 stays $0", () => {
    expect(formFor({ gross_proceeds_usd: "0.00", proceeds_usd: "0.00" }).proceeds_usd).toBe(0);
  });

  it("with no proceeds stored at all opens blank: the save prices it, as a recalculation would", () => {
    const form = formFor({ proceeds_usd: null });
    expect(form.proceeds_usd).toBeUndefined();
    expect(buildTransactionPayload(form, book).proceeds_usd).toBeNull();
  });

  it.each([
    // [stored net, amount, fee, the server's gross (test_old_spend_gross_485.py)]: an exact half cent to even
    ["1.50", "0.01000000", "0.00010000", 1.52],
    ["12.50", "0.01000000", "0.00010000", 12.62],
    ["0.05", "0.02000000", "0.01000000", 0.08],
  ])("rounds %s as the server does", (net, amount, fee, gross) => {
    expect(formFor({ proceeds_usd: net, amount, fee_amount: fee }).proceeds_usd).toBe(gross);
  });
});

describe("an old withdrawal of another purpose with no gross", () => {
  it("one BitcoinTX doesn't know (#61) opens with its stored proceeds, no offset undone", () => {
    const form = formFor({ purpose: "Expenses" });
    expect(form.proceeds_usd).toBe(990.1);
    // Saved, its purpose chosen as Spent, it keeps what it received
    expect(buildTransactionPayload({ ...form, purpose: "Spent" }, book).proceeds_usd).toBe(990.1);
  });

  it("one with none stored (#329) opens blank", () => {
    expect(formFor({ purpose: "Expenses", proceeds_usd: "0.00" }).proceeds_usd).toBeUndefined();
    expect(formFor({ purpose: "Expenses", proceeds_usd: null }).proceeds_usd).toBeUndefined();
  });

  it('an old " spent " (#342) is one 0.8.0 to 0.9.1 didn\'t know: no offset undone', () => {
    const form = formFor({ purpose: " spent " });
    expect(form.purpose).toBe("Spent");
    expect(form.proceeds_usd).toBe(990.1);
  });

  it('an old " spent " with none stored opens at $0, as the server keeps it: shown as Spent, a save keeps it', () => {
    expect(formFor({ purpose: " spent ", proceeds_usd: "0.00" }).proceeds_usd).toBe(0);
    expect(formFor({ purpose: " spent ", proceeds_usd: null }).proceeds_usd).toBe(0);
  });

  it("a gift's stored proceeds were its fee's, never a gross: blank", () => {
    expect(formFor({ purpose: "Gift", proceeds_usd: "10.00" }).proceeds_usd).toBeUndefined();
  });
});
