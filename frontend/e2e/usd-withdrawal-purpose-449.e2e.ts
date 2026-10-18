// #449: a Purpose and FMV chosen for a bitcoin account stayed in the form,
// hidden, when the account changed to Bank, and were saved with the dollar
// withdrawal; the Complete Tax Report then listed it as a gift of bitcoin.
// The same for a deposit's Source.
import { test, expect, listTx, openAddForm, saveForm, seedFunds } from "./fixtures";
import type { Page } from "@playwright/test";

async function lastTx(page: Page) {
  const all = await listTx(page.request);
  return all.reduce((a, b) => ((a.id as number) > (b.id as number) ? a : b));
}

test("a withdrawal moved from the Wallet to Bank is saved without its purpose or FMV", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Withdrawal");
  await page.getByLabel("Date & Time").fill("2024-03-01T10:15:30");
  await page.getByLabel("Account").selectOption("Wallet");
  await page.getByLabel("Purpose").selectOption("Gift");
  await page.getByLabel("FMV (USD)").fill("500");
  await page.getByLabel("Account").selectOption("Bank");
  await expect(page.getByLabel("Purpose")).toHaveCount(0);
  await expect(page.getByLabel("FMV (USD)")).toHaveCount(0);
  await page.getByLabel("Amount").fill("100");
  await saveForm(page);

  const tx = await lastTx(page);
  expect(tx).toMatchObject({ type: "Withdrawal", from_account_id: 1, to_account_id: 99 });
  expect(Number(tx.amount)).toBe(100);
  expect(tx.purpose ?? "N/A").toBe("N/A");
  expect(tx.fmv_usd).toBeNull();
  expect(tx.proceeds_usd).toBeNull();
  // The list shows no purpose for it
  await expect(page.getByText("Gift", { exact: true })).toHaveCount(0);
});

test("a deposit moved from the Wallet to Bank is saved without its source", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill("2024-03-01T10:15:30");
  await page.getByLabel("Account").selectOption("Wallet");
  await page.getByLabel("Source").selectOption("Income");
  await page.getByLabel("Account").selectOption("Bank");
  await expect(page.getByLabel("Source")).toHaveCount(0);
  await page.getByLabel("Amount").fill("2000");
  await saveForm(page);

  const tx = await lastTx(page);
  expect(tx).toMatchObject({ type: "Deposit", from_account_id: 99, to_account_id: 1, source: "N/A" });
  expect(tx.cost_basis_usd).toBeNull();
});
