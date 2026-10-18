// A deposit's Source switched to or from Inherited clears its date, and the
// form still saves, or says why not (#456). WebKit on macOS (the Mac app,
// Safari) kept judging the cleared date input invalid, so Save did nothing
// and said nothing: run it there with E2E_WEBKIT=1 --project=webkit.
import { test, expect, createTx, listTx, openAddForm, saveForm } from "./fixtures";
import type { Page } from "@playwright/test";

const TS = "2024-06-15T03:04:05Z";

async function openEdit(page: Page) {
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
}

test("an Inherited deposit made a Gift saves without a date (#456)", async ({ authedPage: page }) => {
  await createTx(page.request, {
    type: "Deposit", timestamp: TS, from_account_id: 99, to_account_id: 2, amount: "0.01", fee_amount: "0",
    fee_currency: "BTC", source: "Inherited", cost_basis_usd: "500.00", acquired_at: "2024-01-10",
  });
  await openEdit(page);
  await expect(page.getByLabel("Date of death")).toHaveValue("2024-01-10");
  await page.getByLabel("Source").selectOption("Gift");
  await expect(page.getByLabel("Date originally acquired")).toHaveValue("");
  await page.getByLabel("Cost Basis (USD)").fill("40");
  await saveForm(page, "Update Transaction");
  expect((await listTx(page.request))[0]).toMatchObject({ source: "Gift", cost_basis_usd: "40.00", acquired_at: null });
});

test("a new deposit made Inherited, then My BTC, saves without a date (#456)", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account").selectOption("Wallet");
  await page.getByLabel("Amount").fill("0.01");
  await page.getByLabel("Source").selectOption("Inherited");
  await page.getByLabel("Date of death").fill("2024-01-10");
  await page.getByLabel("Source").selectOption("MyBTC");
  await expect(page.getByLabel("Date originally acquired")).toHaveValue("");
  await page.getByLabel("Cost Basis (USD)").fill("40");
  await saveForm(page);
  expect(await listTx(page.request)).toEqual([
    expect.objectContaining({ source: "MyBTC", cost_basis_usd: "40.00", acquired_at: null }),
  ]);
});

test("a dated Gift made Inherited says the date of death is missing (#456)", async ({ authedPage: page }) => {
  await createTx(page.request, {
    type: "Deposit", timestamp: TS, from_account_id: 99, to_account_id: 2, amount: "0.01", fee_amount: "0",
    fee_currency: "BTC", source: "Gift", cost_basis_usd: "50.00", acquired_at: "2015-01-01",
  });
  await openEdit(page);
  await expect(page.getByLabel("Date originally acquired")).toHaveValue("2015-01-01");
  await page.getByLabel("Source").selectOption("Inherited");
  await expect(page.getByLabel("Date of death")).toHaveValue("");
  await page.getByRole("button", { name: "Update Transaction" }).click();
  await expect(page.getByText("Enter the date of death.")).toBeVisible();
  // Typed now, it saves
  await page.getByLabel("Date of death").fill("2024-01-10");
  await saveForm(page, "Update Transaction");
  expect((await listTx(page.request))[0]).toMatchObject({ source: "Inherited", acquired_at: "2024-01-10" });
});
