import { describe, expect, it } from "vitest";
import { feeText, importRequestRows, importRow, importableRows, toEditableRow, typeChange } from "./riverImport";

function proposal(overrides: Partial<RiverProposal> = {}): RiverProposal {
  return {
    row_number: 2,
    date: "2026-02-15T10:00:00Z",
    type: "Transfer",
    from_account: "Exchange BTC",
    to_account: "Wallet",
    amount: "0.00100000",
    type_choices: ["Transfer", "Withdrawal"],
    funding_choices: [],
    basis_autofilled: false,
    status: "new",
    ...overrides,
  };
}

describe("toEditableRow", () => {
  it("ticks every row but one already in the ledger: a row to review is imported (#253)", () => {
    expect(toEditableRow(proposal()).include).toBe(true);
    expect(toEditableRow(proposal({ status: "matched" })).include).toBe(false);
    expect(toEditableRow(proposal({ status: "discrepancy" })).include).toBe(true);
    // A near amount only: most likely the same move typed by hand (the owner's choice)
    expect(toEditableRow(proposal({ status: "discrepancy", near_amount: true })).include).toBe(false);
  });

  it("starts from River's values, with Spent and MyBTC when it has none", () => {
    const row = toEditableRow(proposal({ cost_basis_usd: "12.50", fee_amount: "0.00000500" }));
    expect(row).toMatchObject({
      type: "Transfer", fromAccount: "Exchange BTC", toAccount: "Wallet",
      costBasisUsd: "12.50", feeAmount: "0.00000500", purpose: "Spent", source: "MyBTC",
    });
    expect(toEditableRow(proposal())).toMatchObject({ costBasisUsd: "", feeAmount: "" });
  });
});

describe("feeText (#269)", () => {
  it("writes a fee with its unit: dollars on a Buy or Sell, BTC otherwise", () => {
    const row = (type: string, fee_amount?: string) => toEditableRow(proposal({ type, fee_amount }));
    expect(feeText(row("Buy", "1.50"))).toBe("$1.50");
    expect(feeText(row("Sell", "0.55"))).toBe("$0.55");
    expect(feeText(row("Withdrawal", "0.00000200"))).toBe("0.00000200 BTC");
    expect(feeText(row("Deposit"))).toBe("—");
  });
});

describe("typeChange", () => {
  const sent = toEditableRow(proposal());
  const received = toEditableRow(proposal({ from_account: "Wallet", to_account: "Exchange BTC" }));

  it("gives a withdrawal and a deposit their outside account", () => {
    expect(typeChange(sent, "Withdrawal")).toEqual({ type: "Withdrawal", fromAccount: "Exchange BTC", toAccount: "External" });
    expect(typeChange(received, "Deposit")).toEqual({ type: "Deposit", fromAccount: "External", toAccount: "Exchange BTC" });
  });

  it("keeps a transfer's direction", () => {
    expect(typeChange(sent, "Transfer")).toEqual({ type: "Transfer", fromAccount: "Exchange BTC", toAccount: "Wallet" });
    expect(typeChange(received, "Transfer")).toEqual({ type: "Transfer", fromAccount: "Wallet", toAccount: "Exchange BTC" });
  });
});

describe("importableRows", () => {
  it("takes the ticked rows, one already in the ledger too when it's ticked (#253)", () => {
    const ticked = toEditableRow(proposal({ row_number: 2 }));
    const unticked = { ...toEditableRow(proposal({ row_number: 3 })), include: false };
    const matched = toEditableRow(proposal({ row_number: 4, status: "matched" }));
    expect(importableRows([ticked, unticked, matched])).toEqual([ticked]);
    const tickedMatch = { ...matched, include: true };
    expect(importableRows([ticked, unticked, tickedMatch])).toEqual([ticked, tickedMatch]);
    expect(importRow(tickedMatch).not_a_duplicate).toBe(true);
    expect(importRow(ticked).not_a_duplicate).toBe(false);
  });
});

describe("importRequestRows", () => {
  it("sends the ticked rows, and those in the ledger left unticked as left out (#253)", () => {
    const ticked = toEditableRow(proposal({ row_number: 2 }));
    const unticked = { ...toEditableRow(proposal({ row_number: 3 })), include: false };
    const found = (row_number: number, include: boolean) =>
      ({ ...toEditableRow(proposal({ row_number, status: "matched", matched_tx_id: row_number * 10 })), include });
    const sent = importRequestRows([ticked, unticked, found(4, false), found(5, true)]);
    expect(sent.map((r) => [r.left_out, r.not_a_duplicate, r.matched_tx_id])).toEqual([
      [false, false, null], [true, false, 40], [false, true, 50],
    ]);
    // Ticked, given a mistyped fee, unticked: sent as the preview gave it, so it can't stop the import
    const edited = { ...found(4, false), feeAmount: "0.000006x" };
    expect(importRequestRows([edited])[0]).toMatchObject({ fee_amount: null, left_out: true, matched_tx_id: 40 });
  });
});

describe("importRow", () => {
  it("sends a BTC fee on a transfer, and no source or purpose", () => {
    const row = { ...toEditableRow(proposal()), feeAmount: "0.00000600" };
    expect(importRow(row)).toEqual({
      date: "2026-02-15T10:00:00Z", type: "Transfer", amount: "0.00100000",
      from_account: "Exchange BTC", to_account: "Wallet",
      cost_basis_usd: null, proceeds_usd: null,
      fee_amount: "0.00000600", fee_currency: "BTC", source: null, purpose: null, cost_basis_typed: null,
      price_moment: null, matched_tx_id: null, not_a_duplicate: false, left_out: false,
    });
  });

  it("sends a USD fee on a Buy or Sell, and none when there is no fee", () => {
    const sell = toEditableRow(proposal({ type: "Sell", proceeds_usd: "55.00", fee_amount: "0.55" }));
    expect(importRow(sell)).toMatchObject({ proceeds_usd: "55.00", fee_amount: "0.55", fee_currency: "USD" });
    expect(importRow(toEditableRow(proposal({ type: "Buy" })))).toMatchObject({ fee_amount: null, fee_currency: null });
  });

  it("sends a deposit's source and basis, and a withdrawal's purpose", () => {
    const deposit = { ...toEditableRow(proposal({ type: "Deposit" })), source: "Income", costBasisUsd: "2.10" };
    expect(importRow(deposit)).toMatchObject({ source: "Income", purpose: null, cost_basis_usd: "2.10" });
    const withdrawal = { ...toEditableRow(proposal({ type: "Withdrawal" })), purpose: "Gift" };
    expect(importRow(withdrawal)).toMatchObject({ source: null, purpose: "Gift" });
  });
  it("marks a basis left at the preview's priced value as not typed (#76), with its price's moment", () => {
    const priced = toEditableRow(proposal({
      type: "Deposit", source: "Interest", cost_basis_usd: "2.10", basis_autofilled: true, price_moment: "hour",
    }));
    expect(importRow(priced)).toMatchObject({ cost_basis_usd: "2.10", cost_basis_typed: "no", price_moment: "hour" });
    expect(importRow({ ...priced, costBasisUsd: "3.00" })).toMatchObject({
      cost_basis_usd: "3.00", cost_basis_typed: null, price_moment: null,
    });
  });
});
