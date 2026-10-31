// The form keeps a row's accounts (#351, 2.0 spec 5.13): a Transfer, a Buy
// and a Sell opened and saved unchanged send the ids they were saved with.
// 1.x's form read a Buy back as paid from Exchange USD and every Sell as
// 4 → 3, and refilled a Transfer's To from its From. Only 1.x's ids until a
// route takes an added account (5.10); the form's mounted tests cover a
// second exchange. And a page from before the upgrade can't save.
import { test, expect, createTx, listTx, openAddForm, saveForm, seedFunds, type TxPayload } from "./fixtures";

const TS = "2024-06-15T15:04:05Z";

const KEPT: Array<{ name: string; tx: TxPayload }> = [
  { name: "a Transfer Wallet → Exchange BTC",
    tx: { type: "Transfer", timestamp: TS, from_account_id: 2, to_account_id: 4, amount: "0.2",
      fee_amount: "0.0001", fee_currency: "BTC" } },
  { name: "a Transfer Exchange BTC → Wallet",
    tx: { type: "Transfer", timestamp: TS, from_account_id: 4, to_account_id: 2, amount: "0.2",
      fee_amount: "0.0001", fee_currency: "BTC" } },
  { name: "a consolidation in the Wallet",
    tx: { type: "Transfer", timestamp: TS, from_account_id: 2, to_account_id: 2, amount: "0.2",
      fee_amount: "0.0001", fee_currency: "BTC" } },
  { name: "a dollar Transfer Bank → Exchange USD",
    tx: { type: "Transfer", timestamp: TS, from_account_id: 1, to_account_id: 3, amount: "500",
      fee_amount: "0", fee_currency: "USD" } },
  { name: "a Buy paid from the Bank",
    tx: { type: "Buy", timestamp: TS, from_account_id: 1, to_account_id: 4, amount: "0.1",
      cost_basis_usd: "6000.00", fee_amount: "5", fee_currency: "USD" } },
  { name: "a Buy paid from Exchange USD",
    tx: { type: "Buy", timestamp: TS, from_account_id: 3, to_account_id: 4, amount: "0.1",
      cost_basis_usd: "6000.00", fee_amount: "5", fee_currency: "USD" } },
  { name: "a Sell",
    tx: { type: "Sell", timestamp: TS, from_account_id: 4, to_account_id: 3, amount: "0.1",
      gross_proceeds_usd: "6000", fee_amount: "10", fee_currency: "USD" } },
];

for (const c of KEPT) {
  test(`${c.name}, saved unchanged, keeps its accounts`, async ({ authedPage: page }) => {
    await seedFunds(page.request);
    // Dollars on the exchange and coins in the wallet, so every row above is valid
    await createTx(page.request, {
      type: "Transfer", timestamp: "2024-01-01T12:00:00Z", from_account_id: 1, to_account_id: 3,
      amount: "20000", fee_amount: "0", fee_currency: "USD",
    });
    await createTx(page.request, {
      type: "Transfer", timestamp: "2024-01-02T12:00:00Z", from_account_id: 4, to_account_id: 2,
      amount: "0.5", fee_amount: "0.0001", fee_currency: "BTC",
    });
    const created = await createTx(page.request, c.tx);

    await page.getByRole("link", { name: "Transactions" }).click();
    await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
    const row = page.getByRole("listitem").first();
    await expect(row).toContainText(c.tx.type as string);
    await row.getByRole("button", { name: "Edit" }).click();
    await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
    await saveForm(page, "Update Transaction", { warning: false }); // unchanged: it doesn't ask

    const after = (await listTx(page.request)).find((t) => t.id === created.id)!;
    expect([after.from_account_id, after.to_account_id]).toEqual([c.tx.from_account_id, c.tx.to_account_id]);
    expect(Number(after.amount)).toBe(Number(c.tx.amount));
  });
}

test("a new Buy's Paid from starts blank, and nothing is saved until one is chosen", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Buy");
  await expect(page.getByLabel("Paid from")).toHaveValue("");
  await expect(page.getByLabel("Exchange", { exact: true })).toHaveCount(0); // one exchange: as in 1.x
  await page.getByLabel("Amount USD").fill("1000");
  await page.getByLabel("Amount BTC").fill("0.01");
  await page.getByRole("button", { name: "Save Transaction" }).click();
  await expect(page.getByText("Please select an account")).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(2);
  await page.getByLabel("Paid from").selectOption("Bank");
  await saveForm(page);
  const bought = (await listTx(page.request)).find((t) => t.type === "Buy" && Number(t.amount) === 0.01)!;
  expect([bought.from_account_id, bought.to_account_id]).toEqual([1, 4]);
});

test("a page from before the upgrade can't save: reload it", async ({ authedPage: page }) => {
  // What a 1.x page left open sends: its cookie and the browser's own headers, no X-BitcoinTX-Page
  const answer = await page.evaluate(async () => {
    const r = await fetch("/api/transactions/recalculate", { method: "POST", credentials: "same-origin" });
    return { status: r.status, body: await r.json() };
  });
  expect(answer).toEqual({ status: 409, body: { detail: "BitcoinTX was updated: reload the page." } });
  // This page says its version, so its saves go through
  await seedFunds(page.request);
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account").selectOption("Bank");
  await page.getByLabel("Amount", { exact: true }).fill("5");
  await saveForm(page);
  expect(await listTx(page.request)).toHaveLength(3);
});
