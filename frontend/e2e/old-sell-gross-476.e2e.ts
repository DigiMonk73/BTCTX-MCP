// #476: a Sell saved before BitcoinTX kept a sale's gross (gross_proceeds_usd
// blank, proceeds_usd already net of its USD fee) opens in the edit form with
// the net plus that fee as Gross Proceeds, and saved unchanged keeps every
// figure (a blank gross is read as 0, so the stored net alone isn't shown).
import { test, expect, createTx, listTx, python } from "./fixtures";
import { execFileSync } from "node:child_process";
import path from "node:path";

test("a Sell saved before its gross was kept opens with net plus fee and saves unchanged (#476)", async ({
  app, authedPage: page,
}) => {
  await createTx(page.request, {
    type: "Deposit", timestamp: "2023-01-05T18:00:00Z", from_account_id: 99, to_account_id: 1,
    amount: "50000", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  await createTx(page.request, {
    type: "Buy", timestamp: "2023-01-10T18:00:00Z", from_account_id: 1, to_account_id: 4,
    amount: "1", cost_basis_usd: "20000.00", fee_amount: "0", fee_currency: "USD",
  });
  const sale = await createTx(page.request, {
    type: "Sell", timestamp: "2023-06-01T18:00:00Z", from_account_id: 4, to_account_id: 3,
    amount: "0.05", gross_proceeds_usd: "5000.00", fee_amount: "10", fee_currency: "USD",
  });
  // As a version before 0.8.0 saved it: no gross, the net proceeds stored.
  execFileSync(python(), ["-c",
    "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); " +
    "c.execute('UPDATE transactions SET gross_proceeds_usd=NULL WHERE id=?', (int(sys.argv[2]),)); c.commit()",
    path.join(app.dir, "e2e.db"), String(sale.id)]);
  const old = (await listTx(page.request)).find((t) => t.id === sale.id)!;
  expect(old).toMatchObject({ gross_proceeds_usd: null, proceeds_usd: "4990.00", realized_gain_usd: "3990.00" });

  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").filter({ hasText: "Sell" }).getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await expect(page.getByLabel("Gross Proceeds (USD)")).toHaveValue("5000");
  await expect(page.getByLabel("Fee (USD)")).toHaveValue("10");
  await page.getByRole("button", { name: "Update Transaction" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toHaveCount(0);

  const after = (await listTx(page.request)).find((t) => t.id === sale.id)!;
  expect(after).toMatchObject({ gross_proceeds_usd: "5000.00", proceeds_usd: "4990.00", realized_gain_usd: "3990.00" });
});
