// "Is it a bitcoin account?" by currency, and one copy of the rules (#348, spec 1.4,
// 5.5, 5.13, 5.15): income saved into a wallet added in Settings counts on the
// dashboard, a gift from it gets its value and Ledger Review checks its rows as
// Wallet's; a Buy paid with one exchange's dollars for another's bitcoin is refused
// in 5.5's words; and a row from before 0.9.2 in an account made through the old
// account API is listed until it's saved. Which rows the first 2.0 start keeps is
// the backend's (test_old_rows_348.py): here the list is written into the database.
import { test, expect, createTx, figure, openAddForm, python, saveForm, HISTORICAL_PRICE } from "./fixtures";
import type { APIRequestContext, Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

async function addInSettings(page: Page, label: string, name: string) {
  await page.getByRole("link", { name: "Settings" }).click();
  const section = page.getByRole("region", { name: "Wallets, exchanges and banks" });
  await section.getByRole("button", { name: label }).click();
  const form = section.getByRole("form", { name: label });
  await form.getByLabel("Nickname").fill(name);
  await form.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Added.")).toBeVisible();
}

async function idsByName(request: APIRequestContext): Promise<Record<string, number>> {
  const rows = (await (await request.get("/api/accounts/")).json()) as Array<{ id: number; name: string }>;
  return Object.fromEntries(rows.map((a) => [a.name, a.id]));
}

async function openReview(page: Page) {
  await page.getByRole("link", { name: "Settings" }).click();
  const review = page.getByRole("region", { name: "Ledger review" });
  await review.getByRole("button", { name: "Check again" }).click();
  return review;
}

test("income saved into a wallet added in Settings counts on the dashboard", async ({ authedPage: page }) => {
  await addInSettings(page, "Add a wallet", "Cold Storage");
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill("2024-06-15T10:00");
  await page.getByLabel("Account").selectOption({ label: "Cold Storage" });
  await page.getByLabel("Amount").fill("0.01");
  await page.getByLabel("Source").selectOption("Income");
  await page.getByLabel("Cost Basis (USD)").fill("500");
  await saveForm(page);

  await page.getByRole("link", { name: "Dashboard" }).click();
  expect(await figure(page, "Income")).toBe(500);
  expect(await figure(page, "Total Income")).toBe(500);
});

test("a gift from that wallet gets its value, and Ledger Review checks its deposits", async ({ authedPage: page }) => {
  await addInSettings(page, "Add a wallet", "Cold Storage");
  const cold = (await idsByName(page.request))["Cold Storage"];
  const mine = await createTx(page.request, {
    type: "Deposit", timestamp: "2024-06-01T15:00:00Z", from_account_id: 99, to_account_id: cold,
    amount: "0.5", cost_basis_usd: "20000", fee_amount: "0", fee_currency: "BTC", source: "MyBTC",
  });
  const gift = await createTx(page.request, {
    type: "Withdrawal", timestamp: "2024-07-01T15:00:00Z", from_account_id: cold, to_account_id: 99,
    amount: "0.01", fee_amount: "0", fee_currency: "BTC", purpose: "Gift",
  });
  expect(Number(gift.fmv_usd)).toBe(0.01 * HISTORICAL_PRICE);

  const review = await openReview(page);
  const title = "Reminder: My BTC and Gift deposits counted from their deposit date";
  await expect(review.getByText(`${title}: 1`)).toBeVisible();
  await review.getByRole("button", { name: "Show the 1 deposit" }).click();
  await expect(review.getByRole("list", { name: title })).toContainText(`#${mine.id} · `);
  await expect(review.getByText(/0\.50000000 BTC · Cold Storage —/)).toBeVisible();
});

test("a Buy with one exchange's dollars for another's bitcoin is refused in 5.5's words", async ({ authedPage: page }) => {
  await addInSettings(page, "Add an exchange", "Kraken");
  const ids = await idsByName(page.request);
  const r = await page.request.post("/api/transactions", { data: {
    type: "Buy", timestamp: "2026-01-05T15:00:00Z", from_account_id: ids["Kraken USD"], to_account_id: 4,
    amount: "0.01", cost_basis_usd: "500", fee_amount: "0", fee_currency: "USD",
  } });
  expect(r.status()).toBe(400);
  expect((await r.json()).detail).toBe(
    "A Buy paid from Kraken USD goes into Kraken BTC: an exchange's dollars buy only on that exchange.");
});

test("a row from before 0.9.2 is listed, counts as income, and goes off the list once saved", async ({ app, authedPage: page }) => {
  // As a 1.x ledger has it: account 7 made through the old account API, an income deposit
  // saved into it, and the list its first 2.0 start kept (services/old_rows.py)
  await addInSettings(page, "Add a wallet", "cold2");
  const added = (await idsByName(page.request))["cold2"];
  const old = await createTx(page.request, {
    type: "Deposit", timestamp: "2024-06-15T15:00:00Z", from_account_id: 99, to_account_id: added,
    amount: "0.01", cost_basis_usd: "500", fee_amount: "0", fee_currency: "BTC", source: "Income",
  });
  execFileSync(python(), ["-c",
    "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); a, t = int(sys.argv[2]), int(sys.argv[3]); " +
    "c.execute('UPDATE accounts SET id=7 WHERE id=?', (a,)); " +
    "c.execute('UPDATE transactions SET to_account_id=7 WHERE id=?', (t,)); " +
    "c.execute(\"INSERT OR REPLACE INTO app_settings (key, value) VALUES ('accounts_old_rows', ?)\", ('[%d]' % t,)); " +
    "c.commit()",
    path.join(app.dir, "e2e.db"), String(added), String(old.id)]);
  expect((await page.request.post("/api/transactions/recalculate")).ok()).toBeTruthy();
  await page.reload(); // the accounts list is read once per page

  const review = await openReview(page);
  const title = "Transactions in an account made through BitcoinTX's old account API";
  const list = review.getByRole("list", { name: title });
  await expect(list).toContainText(`#${old.id} · `);
  await expect(list).toContainText("Saved before 0.9.2 into an account made through the old account API");
  await page.getByRole("link", { name: "Dashboard" }).click();
  expect(await figure(page, "Income")).toBe(500);

  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").filter({ hasText: "Income" }).getByRole("button", { name: "Edit" }).click();
  await saveForm(page, "Update Transaction");
  await openReview(page);
  await expect(list).toHaveCount(0);
});
