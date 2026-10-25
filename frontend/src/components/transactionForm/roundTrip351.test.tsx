// @vitest-environment jsdom
// 2.0 spec 5.13's round trip, on the mounted form with its fill-ins (#351):
// for every type and route of 5.5, with accounts numbered from 100 and
// hidden ones, a saved row opened for an edit and saved unchanged sends the
// ids it was saved with, nothing swapped for the first account that fits.
// 1.x's form read a Buy back as paid from Exchange USD into 4, every Sell
// as 4 → 3, and refilled a Transfer's To from its From. A row naming an
// account the book lacks shows it as missing, with its picker empty, and
// isn't saved until another is chosen.
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MANY, MISSING_ID, ONE_OF_EACH } from "../../test/books";
import { renderForm, shown } from "../../test/renderForm";

type Row = NonNullable<Parameters<typeof renderForm>[0]["transaction"]>;

const btcDeposit = (to: number): Row => ({
  id: 7, type: "Deposit", from_account_id: 99, to_account_id: to, amount: "0.1", fee_amount: "0",
  fee_currency: "BTC", source: "MyBTC", cost_basis_usd: "1000",
});
const usdDeposit = (to: number): Row => ({
  id: 7, type: "Deposit", from_account_id: 99, to_account_id: to, amount: "500", fee_amount: "0",
  fee_currency: "USD", source: "N/A",
});
const btcWithdrawal = (from: number): Row => ({
  id: 7, type: "Withdrawal", from_account_id: from, to_account_id: 99, amount: "0.1", fee_amount: "0.0001",
  fee_currency: "BTC", purpose: "Gift", fmv_usd: "1000",
});
const usdWithdrawal = (from: number): Row => ({
  id: 7, type: "Withdrawal", from_account_id: from, to_account_id: 99, amount: "100", fee_amount: "0",
  fee_currency: "USD", purpose: "N/A",
});
const btcTransfer = (from: number, to: number): Row => ({
  id: 7, type: "Transfer", from_account_id: from, to_account_id: to, amount: "0.2", fee_amount: "0.0001",
  fee_currency: "BTC",
});
const usdTransfer = (from: number, to: number): Row => ({
  id: 7, type: "Transfer", from_account_id: from, to_account_id: to, amount: "500", fee_amount: "2",
  fee_currency: "USD",
});
const buy = (from: number, to: number): Row => ({
  id: 7, type: "Buy", from_account_id: from, to_account_id: to, amount: "0.1", cost_basis_usd: "6000",
  fee_amount: "5", fee_currency: "USD",
});
const sell = (from: number, to: number): Row => ({
  id: 7, type: "Sell", from_account_id: from, to_account_id: to, amount: "0.1", gross_proceeds_usd: "6000",
  proceeds_usd: "5990", fee_amount: "10", fee_currency: "USD",
});

// Every route of 5.5 that 1.x had, with one of each
const ONE_OF_EACH_ROWS: Row[] = [
  usdDeposit(1), btcDeposit(2), usdDeposit(3), btcDeposit(4),
  usdWithdrawal(1), btcWithdrawal(2), usdWithdrawal(3), btcWithdrawal(4),
  usdTransfer(1, 3), usdTransfer(3, 1), btcTransfer(2, 4), btcTransfer(4, 2), btcTransfer(2, 2), btcTransfer(4, 4),
  buy(1, 4), buy(3, 4), sell(4, 3),
];

// And 2.0's: between two accounts of a kind, on a second exchange, from and into hidden accounts
const MANY_ROWS: Row[] = [
  usdDeposit(101), btcDeposit(100), btcDeposit(104), usdDeposit(102), btcDeposit(103), btcDeposit(106),
  usdWithdrawal(101), btcWithdrawal(100), btcWithdrawal(104), usdWithdrawal(102), btcWithdrawal(103),
  // Transfers from Bank, Wallet and Exchange BTC into a second account
  usdTransfer(1, 101), btcTransfer(2, 100), btcTransfer(4, 103),
  usdTransfer(101, 102), usdTransfer(3, 102), usdTransfer(102, 1), btcTransfer(100, 103), btcTransfer(103, 4),
  btcTransfer(100, 100), btcTransfer(103, 103), btcTransfer(104, 2), btcTransfer(2, 104), usdTransfer(105, 1),
  buy(1, 103), buy(101, 4), buy(102, 103), buy(105, 106), buy(1, 106),
  sell(103, 102), sell(106, 105),
];

const route = (row: Row) => `${row.type} ${row.from_account_id} → ${row.to_account_id}`;

async function savedUnchanged(book: AccountBook, row: Row) {
  const form = await renderForm({ book, transaction: row });
  await form.save();
  form.unmount();
  return form.sent();
}

describe("a row saved unchanged keeps its accounts", () => {
  it.each(ONE_OF_EACH_ROWS.map((row) => [route(row), row] as const))("one of each: %s", async (_name, row) => {
    expect(await savedUnchanged(ONE_OF_EACH, row)).toMatchObject({
      from_account_id: row.from_account_id, to_account_id: row.to_account_id, fee_currency: row.fee_currency,
    });
  });

  it.each(MANY_ROWS.map((row) => [route(row), row] as const))("ids from 100, hidden ones: %s", async (_name, row) => {
    expect(await savedUnchanged(MANY, row)).toMatchObject({
      from_account_id: row.from_account_id, to_account_id: row.to_account_id, fee_currency: row.fee_currency,
    });
  });

  it("and its amounts", async () => {
    expect(await savedUnchanged(MANY, btcTransfer(2, 100))).toMatchObject({ amount: 0.2, fee_amount: 0.0001 });
    expect(await savedUnchanged(MANY, usdTransfer(1, 101))).toMatchObject({ amount: 500, fee_amount: 2 });
    expect(await savedUnchanged(MANY, buy(102, 103))).toMatchObject({ amount: 0.1, cost_basis_usd: 6000, fee_amount: 5 });
    expect(await savedUnchanged(MANY, sell(103, 102))).toMatchObject({ amount: 0.1, gross_proceeds_usd: 6000 });
  });

  it("an edit's new From never makes its To a consolidation, nor a saved consolidation a transfer (#719)", async () => {
    const moved = await renderForm({ book: ONE_OF_EACH, transaction: btcTransfer(4, 2) });
    await moved.choose("From Account", "Wallet");
    expect(shown("To Account")).toBe("Select To Account");
    await moved.save();
    expect(moved.sent()).toBeUndefined();
    moved.unmount();
    const consolidation = await renderForm({ book: ONE_OF_EACH, transaction: btcTransfer(2, 2) });
    expect(shown("To Account")).toBe("Wallet: consolidate within the same wallet");
    await consolidation.choose("From Account", "Exchange BTC");
    expect(shown("To Account")).toBe("Select To Account");
    await consolidation.save();
    expect(consolidation.sent()).toBeUndefined();
    // A To chosen since is a move into it, even back to the row's own From
    await consolidation.choose("To Account", "Wallet");
    await consolidation.choose("From Account", "Wallet");
    expect(shown("To Account")).toBe("Select To Account");
  });

  it("showing a hidden account it names", async () => {
    await renderForm({ book: MANY, transaction: btcTransfer(104, 2) });
    expect([shown("From Account"), shown("To Account")]).toEqual(["Old phone", "Sparrow"]);
  });

  it("showing a second exchange's Buy as bought there", async () => {
    await renderForm({ book: MANY, transaction: buy(102, 103) });
    expect([shown("Exchange"), shown("Paid from")]).toEqual(["Kraken", "Kraken USD"]);
  });
});

describe("a row naming a missing account", () => {
  it.each([
    ["a Deposit into it", { ...btcDeposit(MISSING_ID) }, "Account"],
    ["a Withdrawal from it", { ...btcWithdrawal(MISSING_ID) }, "Account"],
    ["a Transfer into it", { ...btcTransfer(2, MISSING_ID) }, "To Account"],
    ["a Transfer from it", { ...btcTransfer(MISSING_ID, 2) }, "From Account"],
    ["a Sell from it", { ...sell(MISSING_ID, 3) }, "Exchange"],
  ] as const)("%s: shown as missing, the picker empty, not saved", async (_name, row, label) => {
    const form = await renderForm({ book: ONE_OF_EACH, transaction: row });
    expect(screen.getByText(`account ${MISSING_ID} (missing)`)).toBeTruthy();
    expect(shown(label)).toMatch(/^Select/);
    await form.save();
    expect(form.sent()).toBeUndefined();
  });

  it("keeps the row's other account while the missing one is chosen again", async () => {
    const transfer = await renderForm({ book: MANY, transaction: btcTransfer(MISSING_ID, 100) });
    await transfer.choose("From Account", "Sparrow");
    expect(shown("To Account")).toBe("Coldcard");
    transfer.unmount();
    const bought = await renderForm({ book: ONE_OF_EACH, transaction: buy(1, MISSING_ID) });
    await bought.choose("Exchange", "Exchange");
    await bought.save();
    expect(bought.sent()).toMatchObject({ from_account_id: 1, to_account_id: 4 });
  });

  it("saved into the account chosen instead", async () => {
    const form = await renderForm({ book: MANY, transaction: btcTransfer(2, MISSING_ID) });
    await form.choose("To Account", "Coldcard");
    await form.save();
    expect(form.sent()).toMatchObject({ from_account_id: 2, to_account_id: 100 });
  });
});
