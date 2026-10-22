// #352's done-when (B6b, spec 5.8), clicked through: a save, an edit and a
// delete that change an earlier tax year ask first, in the past-year warning's
// dialog, and save only on "Save anyway (a copy is made first)"; Cancel saves
// nothing; an add's box lets that year's next adds through while the page is
// open, and a reload asks again. Edits always ask. The server's "this tax year"
// is today's, so every row dated 2023 is in an earlier one.
import { test, expect, createTx, listTx, openAddForm, pastYearsDialog, type TxPayload } from "./fixtures";
import type { Page } from "@playwright/test";

const SAVE = "Save anyway (a copy is made first)";
const BOX = "Don't ask again for adds to 2023 while this page is open";

const DEPOSIT: TxPayload = {
  type: "Deposit", timestamp: "2023-02-01T18:00:00Z", from_account_id: 99, to_account_id: 2,
  amount: "1", fee_amount: "0", fee_currency: "BTC", source: "MyBTC", cost_basis_usd: "20000",
};
const SPEND: TxPayload = {
  type: "Withdrawal", timestamp: "2023-06-01T18:00:00Z", from_account_id: 2, to_account_id: 99,
  amount: "0.5", fee_amount: "0", fee_currency: "BTC", purpose: "Spent", proceeds_usd: "15000",
};

/** Add Transaction: an income Deposit into Wallet on `day`, then Save. */
async function addIncome(page: Page, day: string) {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill(`${day}T09:00:05`); // with seconds: the field keeps them
  await page.getByLabel("Account").selectOption("Wallet");
  await page.getByLabel("Amount").fill("0.01");
  await page.getByLabel("Source").selectOption("Income");
  await page.getByRole("button", { name: "Save Transaction" }).click();
}

/** Open the list's row of `type` to edit it. */
async function openRow(page: Page, type: string) {
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").filter({ hasText: type }).first().getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
}

test.describe("the past-year warning (#352)", () => {
  test("an add into an earlier year asks, Cancel saves nothing, Save anyway saves", async ({ authedPage: page }) => {
    await createTx(page.request, DEPOSIT);
    await createTx(page.request, SPEND);
    await addIncome(page, "2023-03-01");
    const dialog = pastYearsDialog(page);
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText("which you may already have filed");
    await expect(dialog).toContainText("2023");
    await expect(dialog.getByRole("list", { name: "What changes" })).toBeVisible();

    await dialog.getByRole("button", { name: "Cancel" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Add Transaction" })).toBeVisible(); // the form stays
    expect(await listTx(page.request)).toHaveLength(2);

    await page.getByRole("button", { name: "Save Transaction" }).click();
    await dialog.getByRole("button", { name: SAVE }).click();
    await expect(page.getByRole("heading", { name: "Add Transaction" })).toHaveCount(0);
    expect(await listTx(page.request)).toHaveLength(3);
  });

  test("Escape in the dialog cancels it and keeps the panel open", async ({ authedPage: page }) => {
    await createTx(page.request, DEPOSIT);
    await addIncome(page, "2023-01-15");
    await expect(pastYearsDialog(page)).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(pastYearsDialog(page)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "Add Transaction" })).toBeVisible();
    expect(await listTx(page.request)).toHaveLength(1);
  });

  test("the box lets that year's next adds through until a reload", async ({ authedPage: page }) => {
    await createTx(page.request, DEPOSIT);
    await addIncome(page, "2023-03-01");
    await pastYearsDialog(page).getByRole("checkbox", { name: BOX }).check();
    await pastYearsDialog(page).getByRole("button", { name: SAVE }).click();
    await expect(page.getByRole("heading", { name: "Add Transaction" })).toHaveCount(0);

    await addIncome(page, "2023-04-01");
    await expect(page.getByRole("heading", { name: "Add Transaction" })).toHaveCount(0);
    await expect(pastYearsDialog(page)).toHaveCount(0);
    expect(await listTx(page.request)).toHaveLength(3);

    await page.reload();
    await addIncome(page, "2023-05-01");
    await expect(pastYearsDialog(page)).toBeVisible();
  });

  test("an edit and a delete always ask", async ({ authedPage: page }) => {
    await createTx(page.request, DEPOSIT);
    await createTx(page.request, SPEND);
    await openRow(page, "Deposit");
    await page.getByLabel("Cost Basis (USD)").fill("25000");
    await page.getByRole("button", { name: "Update Transaction" }).click();
    const dialog = pastYearsDialog(page);
    await expect(dialog.getByRole("checkbox")).toHaveCount(0);
    await expect(dialog.getByRole("list", { name: "What changes" })).toContainText("Withdrawal");
    await dialog.getByRole("button", { name: SAVE }).click();
    await expect(page.getByRole("heading", { name: "Edit Transaction" })).toHaveCount(0);
    const spend = (await listTx(page.request)).find((t) => t.type === "Withdrawal");
    expect(Number(spend?.cost_basis_usd)).toBe(12500);

    await openRow(page, "Withdrawal");
    page.once("dialog", (d) => d.accept()); // "Are you sure?"
    await page.getByRole("button", { name: "Delete" }).click();
    await expect(dialog).toContainText("Deleted.");
    await dialog.getByRole("button", { name: SAVE }).click();
    await expect(page.getByRole("heading", { name: "Edit Transaction" })).toHaveCount(0);
    expect(await listTx(page.request)).toHaveLength(1);
  });
});
