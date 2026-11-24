// The coins a sale uses, in the Sell form (#960): read-only, each with its
// date acquired, amount, cost, proceeds, gain and term, as the save will
// record them and Form 8949 print them; the same when the saved sale is
// opened again.
import { test, expect, openAddForm, saveForm, seedFunds } from "./fixtures";

test("a sale lists the coins it uses, and its edit the same (#960)", async ({ authedPage: page }) => {
  await seedFunds(page.request); // 1 BTC bought 2023-01-10 for $20,000, on the exchange
  await openAddForm(page, "Sell");
  await page.getByLabel("Date & Time").fill("2025-03-01T09:00:05");
  await page.getByLabel("Amount BTC").fill("0.4");
  await page.getByLabel("Gross Proceeds (USD)").fill("40000");
  const table = page.getByRole("table", { name: "Coins this sale uses" });
  await expect(table.getByRole("row").nth(1)).toHaveText(
    /Jan 10, 2023\s*0\.40000000\s*\$8,000\.00\s*\$40,000\.00\s*\$32,000\.00\s*Long-term/);
  await expect(page.getByRole("button", { name: "Choose which coins leave" })).toHaveCount(0);
  await saveForm(page);

  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
  await page.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Coins this sale uses" }).getByRole("row").nth(1)).toHaveText(
    /Jan 10, 2023\s*0\.40000000\s*\$8,000\.00\s*\$40,000\.00\s*\$32,000\.00\s*Long-term/);
});
