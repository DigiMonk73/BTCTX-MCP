// #485: a Spent withdrawal saved before BitcoinTX kept a withdrawal's gross
// (gross_proceeds_usd blank, proceeds_usd the net that version stored, its
// BTC fee's offset taken off) opens in the edit form with the gross the
// server recovers for it, and saved unchanged keeps it. It opened with $0,
// and the save made it a $0 sale.
import { test, expect, createTx, listTx, python, seedFunds, saveForm } from "./fixtures";
import { execFileSync } from "node:child_process";
import path from "node:path";

test("a Spent saved before its gross was kept opens with that gross and saves unchanged (#485)", async ({
  app, authedPage: page,
}) => {
  await seedFunds(page.request);
  const spend = await createTx(page.request, {
    type: "Withdrawal", timestamp: "2024-06-01T18:00:00Z", from_account_id: 4, to_account_id: 99, amount: "0.01",
    fee_amount: "0.0001", fee_currency: "BTC", purpose: "Spent", proceeds_usd: "1000",
  });
  // As a version before 0.8.0 saved it: no gross, the net with the fee's offset taken off (1000 x 0.01 / 0.0101).
  execFileSync(python(), ["-c",
    "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); " +
    "c.execute('UPDATE transactions SET gross_proceeds_usd=NULL, proceeds_usd=990.10 WHERE id=?', " +
    "(int(sys.argv[2]),)); c.commit()",
    path.join(app.dir, "e2e.db"), String(spend.id)]);
  const old = (await listTx(page.request)).find((t) => t.id === spend.id)!;
  expect(old).toMatchObject({ gross_proceeds_usd: null, proceeds_usd: "990.10" });

  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").filter({ hasText: "Withdrawal" }).getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await expect(page.getByLabel("Proceeds (USD)")).toHaveValue("1000");
  await expect(page.getByText('"Proceeds (USD)" is 0')).toHaveCount(0);
  await saveForm(page, "Update Transaction");

  const after = (await listTx(page.request)).find((t) => t.id === spend.id)!;
  expect(after).toMatchObject({ gross_proceeds_usd: "1000.00", proceeds_from_price: false });
  // The spend's fee is a cost of it: its proceeds are the gross less the fee's value (#157)
  expect(Number(after.proceeds_usd)).toBeCloseTo(1000 - Number(after.fee_usd), 2);
  expect(Number(after.realized_gain_usd)).toBeGreaterThan(0);
});
