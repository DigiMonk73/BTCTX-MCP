// Editing one field changes only that field; the time survives to the second
// in every timezone (the v0.9.1 bug shifted it by the UTC offset).
import { test, expect, createTx, listTx, seedFunds, saveForm, type TxPayload } from "./fixtures";
import type { Page } from "@playwright/test";

// 03:04:05 UTC: the previous evening in Chicago, midday in Tokyo.
const TS = "2024-06-15T03:04:05Z";

const NUMERIC = ["amount", "fee_amount", "cost_basis_usd", "proceeds_usd", "gross_proceeds_usd",
  "realized_gain_usd", "fmv_usd"];

function normalize(tx: Record<string, unknown>) {
  const out: Record<string, unknown> = { ...tx };
  // The form sends 0 for fields it doesn't use, so an API-created null reads
  // back as 0 after a UI save (finding F5); treat them as the same here.
  for (const k of NUMERIC) out[k] = Number(out[k] ?? 0);
  out.timestamp = new Date(tx.timestamp as string).toISOString();
  delete out.updated_at;
  return out;
}

/** Open the most recently added transaction in the edit panel. */
async function openEdit(page: Page, type: string) {
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
  const row = page.getByRole("listitem").first();
  await expect(row).toContainText(type);
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await expect(page.getByLabel("Transaction Type")).toHaveValue(type);
  await expect(page.getByLabel("Transaction Type")).toBeDisabled();
}

const CASES: Array<{
  name: string;
  tx: TxPayload;
  field: string;
  value: string;
  changes: Record<string, unknown>;
}> = [
  {
    name: "Deposit (income): change the amount",
    tx: { type: "Deposit", timestamp: TS, from_account_id: 99, to_account_id: 2, amount: "0.01",
      cost_basis_usd: "600.00", source: "Income", fee_amount: "0", fee_currency: "BTC" },
    field: "Amount", value: "0.02", changes: { amount: 0.02 },
  },
  {
    name: "Withdrawal (spent): change the proceeds",
    tx: { type: "Withdrawal", timestamp: TS, from_account_id: 4, to_account_id: 99, amount: "0.1",
      proceeds_usd: "6000", purpose: "Spent", fee_amount: "0", fee_currency: "BTC" },
    field: "Proceeds (USD)", value: "6500",
    changes: { gross_proceeds_usd: 6500, proceeds_usd: 6500, realized_gain_usd: 4500 },
  },
  {
    name: "Transfer with a BTC fee: change the amount received",
    tx: { type: "Transfer", timestamp: TS, from_account_id: 4, to_account_id: 2, amount: "0.5",
      fee_amount: "0.0001", fee_currency: "BTC" },
    field: "Amount (To)", value: "0.4998", changes: { fee_amount: 0.0002, fee_usd: "10.00" }, // the fee changed, so it is valued again
  },
  {
    name: "Buy: change the fee",
    tx: { type: "Buy", timestamp: TS, from_account_id: 1, to_account_id: 4, amount: "0.1",
      cost_basis_usd: "6000.00", fee_amount: "5", fee_currency: "USD" },
    field: "Fee (USD)", value: "7", changes: { fee_amount: 7 },
  },
  {
    name: "Sell: change the gross proceeds",
    tx: { type: "Sell", timestamp: TS, from_account_id: 4, to_account_id: 3, amount: "0.1",
      gross_proceeds_usd: "6000", fee_amount: "10", fee_currency: "USD" },
    field: "Gross Proceeds (USD)", value: "6100",
    changes: { gross_proceeds_usd: 6100, proceeds_usd: 6090, realized_gain_usd: 4090 },
  },
];

for (const c of CASES) {
  test(`edit ${c.name}; nothing else changes`, async ({ authedPage: page }) => {
    await seedFunds(page.request);
    const created = await createTx(page.request, c.tx);
    const before = normalize(created);

    await openEdit(page, c.tx.type as string);
    // The form shows the stored time as local wall-clock time, to the second.
    const local = await page.evaluate((iso) => {
      const d = new Date(iso);
      const p = (n: number) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
    }, TS);
    await expect(page.getByLabel("Date & Time")).toHaveValue(local);

    await page.getByLabel(c.field).fill(c.value);
    await saveForm(page, "Update Transaction");

    const after = normalize((await listTx(page.request)).find((t) => t.id === created.id)!);
    expect(after).toEqual({ ...before, ...c.changes });
  });
}

test("saving an edit without changes changes nothing", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  const created = await createTx(page.request, CASES[4].tx);
  await openEdit(page, "Sell");
  await saveForm(page, "Update Transaction");
  const after = (await listTx(page.request)).find((t) => t.id === created.id)!;
  expect(normalize(after)).toEqual(normalize(created));
});

test("delete asks twice, then removes the transaction", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await createTx(page.request, CASES[4].tx);
  const dialogs: string[] = [];
  page.on("dialog", (d) => {
    dialogs.push(d.message());
    void d.accept();
  });
  await openEdit(page, "Sell");
  await page.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toHaveCount(0);
  expect(dialogs).toEqual([
    "Are you sure you want to delete this transaction?",
    "Are you sure you want to delete this transaction?",
  ]);
  expect((await listTx(page.request)).map((t) => t.type).sort()).toEqual(["Buy", "Deposit"]);
  await expect(page.getByRole("listitem").filter({ hasText: "Sell" })).toHaveCount(0);
});

test("cancelling delete keeps the transaction", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await createTx(page.request, CASES[4].tx);
  page.on("dialog", (d) => void d.dismiss());
  await openEdit(page, "Sell");
  await page.getByRole("button", { name: "Delete" }).click();
  expect(await listTx(page.request)).toHaveLength(3);
});
