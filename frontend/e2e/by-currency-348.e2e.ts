// "Is it a bitcoin account?" by currency (#348, spec 1.4, 5.3, 5.13, 5.15; the
// owner's decision S7): a row from before 0.9.2 in an account made through 1.x's
// account API counts by that account's currency, so its income is on the dashboard,
// and Ledger Review lists it until it's saved or deleted. Which rows the first 2.0
// start keeps is the backend's (test_old_rows_348.py): here the database is written
// as that start leaves it. Saving into a wallet added in Settings waits for the gate
// (B7a) and Settings' accounts (B7b), whose own specs click it through.
import { test, expect, createTx, figure, python, openSection } from "./fixtures";
import type { Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

async function openReview(page: Page) {
  await page.getByRole("link", { name: "Settings" }).click();
  await openSection(page, "Ledger Review");
  const review = page.getByRole("region", { name: "Ledger review" });
  await review.getByRole("button", { name: "Check again" }).click();
  return review;
}

test("a row from before 0.9.2 counts as income and is listed until it's deleted", async ({ app, authedPage: page }) => {
  // As a 1.x ledger has it: account 7 made through the old account API, an income
  // deposit saved into it, and the list its first 2.0 start kept (services/old_rows.py)
  const old = await createTx(page.request, {
    type: "Deposit", timestamp: "2024-06-15T15:00:00Z", from_account_id: 99, to_account_id: 2,
    amount: "0.01", cost_basis_usd: "500", fee_amount: "0", fee_currency: "BTC", source: "Income",
  });
  execFileSync(python(), ["-c",
    "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); t = int(sys.argv[2]); " +
    "c.execute(\"INSERT INTO accounts (id, user_id, name, currency, kind, hidden) VALUES (7, 1, 'cold2', 'BTC', 'wallet', 0)\"); " +
    "c.execute('UPDATE transactions SET to_account_id=7 WHERE id=?', (t,)); " +
    "c.execute(\"INSERT OR REPLACE INTO app_settings (key, value) VALUES ('accounts_old_rows', ?)\", ('[%d]' % t,)); " +
    "c.commit()",
    path.join(app.dir, "e2e.db"), String(old.id)]);
  expect((await page.request.post("/api/transactions/recalculate")).ok()).toBeTruthy();
  await page.reload();

  const review = await openReview(page);
  const title = "Transactions in an account made through BitcoinTX's old account API";
  const list = review.getByRole("list", { name: title });
  await expect(list).toContainText(`#${old.id} · `);
  await expect(list).toContainText("Saved before 0.9.2 into an account made through the old account API");
  await page.getByRole("link", { name: "Dashboard" }).click();
  expect(await figure(page, "Income")).toBe(500);

  expect((await page.request.delete(`/api/transactions/${old.id}`)).ok()).toBeTruthy();
  await openReview(page);
  await expect(list).toHaveCount(0);
});
