// The past-year warning's dialog (2.0 spec 5.8, card B6b #352): a save that
// changes an earlier tax year asks first, naming the years and what changes,
// and saves only after "Save anyway (a copy is made first)", a copy of the
// database kept in the data folder's backups. An add offers to stop asking for
// that year's adds while the page is open (the owner's decision, 2026-10-16);
// edits always ask, and a reload asks again. The server's clock is the real
// one: these rows are all in earlier tax years.
import { readdirSync } from "node:fs";
import path from "node:path";
import type { Page } from "@playwright/test";
import { test, expect, createTx, listTx, openAddForm, seedFunds, SAVE_ANYWAY } from "./fixtures";

function warning(page: Page) {
  return page.getByRole("dialog").filter({ has: page.getByRole("button", { name: SAVE_ANYWAY }) });
}

async function addWalletDeposit(page: Page, when: string, amount: string) {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill(when);
  await page.getByLabel("Account").selectOption("Wallet");
  await page.getByLabel("Amount").fill(amount);
  await page.getByLabel("Source").selectOption("MyBTC");
  await page.getByLabel("Cost Basis (USD)").fill("1000");
  await page.getByRole("button", { name: "Save Transaction" }).click();
}

function copies(dir: string): string[] {
  return readdirSync(path.join(dir, "backups")).filter((f) => f.startsWith("e2e-pre-change-past-year-"));
}

test("an add into an earlier year asks: Cancel saves nothing, Save anyway saves after a copy", async ({
  app, authedPage: page,
}) => {
  await seedFunds(page.request);
  await addWalletDeposit(page, "2022-06-01T12:00:00", "0.1"); // before every row: a backdated add
  const dialog = warning(page);
  await expect(dialog).toContainText("This changes the figures of tax year 2022, which you may already have filed.");
  await expect(dialog).toContainText("Deposit");
  await dialog.getByRole("button", { name: "Cancel" }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Add Transaction" })).toBeVisible(); // what was typed stays
  await expect(page.getByLabel("Amount")).toHaveValue("0.1");
  expect(await listTx(page.request)).toHaveLength(2);

  await page.getByRole("button", { name: "Save Transaction" }).click();
  await dialog.getByRole("button", { name: SAVE_ANYWAY }).click();
  await expect(page.getByRole("heading", { name: "Add Transaction" })).toHaveCount(0);
  expect(await listTx(page.request)).toHaveLength(3);
  expect(copies(app.dir)).toHaveLength(1);
});

test("the box stops the asking for that year's adds while the page is open; a reload asks again", async ({
  authedPage: page,
}) => {
  await seedFunds(page.request); // rows of 2023: adds to 2024 come after every one
  await addWalletDeposit(page, "2024-02-01T12:00:00", "0.1");
  const dialog = warning(page);
  await expect(dialog).toContainText("This adds to tax year 2024, which you may already have filed.");
  await dialog.getByLabel("Don't ask again for adds to 2024 while this page is open").check();
  await dialog.getByRole("button", { name: SAVE_ANYWAY }).click();
  await expect(page.getByRole("heading", { name: "Add Transaction" })).toHaveCount(0);

  await addWalletDeposit(page, "2024-03-01T12:00:00", "0.2"); // confirmed by the page itself
  await expect(page.getByRole("heading", { name: "Add Transaction" })).toHaveCount(0);
  expect(await listTx(page.request)).toHaveLength(4);

  await addWalletDeposit(page, "2025-03-01T12:00:00", "0.3"); // another year asks
  await expect(warning(page)).toContainText("tax year 2025");
  await warning(page).getByRole("button", { name: "Cancel" }).click();

  await page.reload();
  await addWalletDeposit(page, "2024-04-01T12:00:00", "0.4");
  await expect(warning(page)).toContainText("tax year 2024");
});

test("an edit asks, with no box", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await createTx(page.request, {
    type: "Sell", timestamp: "2024-03-01T15:00:00Z", from_account_id: 4, to_account_id: 3,
    amount: "0.1", gross_proceeds_usd: "9000", fee_amount: "0", fee_currency: "USD",
  });
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").filter({ hasText: "Sell" }).getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Gross Proceeds (USD)").fill("9500");
  await page.getByRole("button", { name: "Update Transaction" }).click();
  const dialog = warning(page);
  await expect(dialog).toContainText("This changes the figures of tax year 2024");
  await expect(dialog).toContainText("proceeds 9000.00 -> 9500.00");
  await expect(dialog.getByRole("checkbox")).toHaveCount(0);
  await dialog.getByRole("button", { name: SAVE_ANYWAY }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toHaveCount(0);
  const sale = (await listTx(page.request)).find((t) => t.type === "Sell")!;
  expect(Number(sale.gross_proceeds_usd)).toBe(9500);
});

test("a save dated this year doesn't ask", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Deposit"); // dated now by default
  await page.getByLabel("Account").selectOption("Wallet");
  await page.getByLabel("Amount").fill("0.1");
  await page.getByLabel("Source").selectOption("MyBTC");
  await page.getByLabel("Cost Basis (USD)").fill("1000");
  await page.getByRole("button", { name: "Save Transaction" }).click();
  await expect(page.getByRole("heading", { name: "Add Transaction" })).toHaveCount(0);
  await expect(warning(page)).toHaveCount(0);
});
