// A dollar transfer works as a bitcoin one does (#447): you type what left
// (Amount (From)) and what arrived (Amount (To)), and Fee (USD) is the
// difference, which can't be typed. It's saved as dollar transfers always
// were (amount = what arrived, the fee on top), so one saved before opens
// and saves with the same figures.
import { test, expect, createTx, listTx, openAddForm, saveForm } from "./fixtures";
import type { Page } from "@playwright/test";

async function balances(page: Page): Promise<Record<string, number>> {
  const r = await page.request.get("/api/calculations/accounts/balances");
  const rows = (await r.json()) as Array<{ name: string; balance: string }>;
  return Object.fromEntries(rows.map((b) => [b.name, Number(b.balance)]));
}

async function openNewestEdit(page: Page) {
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
  await page.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
}

const BANK_DEPOSIT = {
  type: "Deposit", timestamp: "2024-01-02T18:00:00Z", from_account_id: 99, to_account_id: 1,
  amount: "2000", fee_amount: "0", fee_currency: "USD", source: "N/A",
};

test("Bank → Exchange: $1,000 sent, $990 arrived, a $10 fee (#447)", async ({ authedPage: page }) => {
  await createTx(page.request, BANK_DEPOSIT);
  await openAddForm(page, "Transfer");
  await page.getByLabel("Date & Time").fill("2024-03-01T10:15:30");
  await page.getByLabel("From Account").selectOption("Bank");
  await expect(page.getByLabel("To Account")).toHaveValue("Exchange USD");
  await page.getByLabel("Amount (From)").fill("1000");
  await page.getByLabel("Amount (To)").fill("990");
  const fee = page.getByLabel("Fee (USD)");
  await expect(fee).toHaveValue("10");
  await expect(fee).toHaveAttribute("readonly", "");
  await saveForm(page);

  const saved = (await listTx(page.request)).find((t) => t.type === "Transfer")!;
  expect(saved).toMatchObject({ from_account_id: 1, to_account_id: 3, fee_currency: "USD" });
  expect([Number(saved.amount), Number(saved.fee_amount)]).toEqual([990, 10]);
  const by = await balances(page);
  expect([by["Bank"], by["Exchange USD"], by["USD Fees"]]).toEqual([1000, 990, 10]);

  // It opens as typed
  await openNewestEdit(page);
  await expect(page.getByLabel("Amount (From)")).toHaveValue("1000");
  await expect(page.getByLabel("Amount (To)")).toHaveValue("990");
  await expect(page.getByLabel("Fee (USD)")).toHaveValue("10");
});

test("one saved before #447 opens as From = amount + fee and saves the same figures", async ({ authedPage: page }) => {
  await createTx(page.request, BANK_DEPOSIT);
  // As the old form saved "$1,000, fee $10": $1,010 left the bank
  const old = await createTx(page.request, {
    type: "Transfer", timestamp: "2024-03-01T16:15:30Z", from_account_id: 1, to_account_id: 3,
    amount: "1000", fee_amount: "10", fee_currency: "USD",
  });
  const before = await balances(page);
  expect([before["Bank"], before["Exchange USD"]]).toEqual([990, 1000]);

  await openNewestEdit(page);
  await expect(page.getByLabel("Amount (From)")).toHaveValue("1010");
  await expect(page.getByLabel("Amount (To)")).toHaveValue("1000");
  await expect(page.getByLabel("Fee (USD)")).toHaveValue("10");
  await saveForm(page, "Update Transaction", { warning: false }); // dollars only: it never asks

  const after = (await listTx(page.request)).find((t) => t.id === old.id)!;
  expect([Number(after.amount), Number(after.fee_amount), after.fee_currency]).toEqual([1000, 10, "USD"]);
  expect(await balances(page)).toEqual(before);
});

test("Exchange → Bank: what arrived above what left is refused, in words", async ({ authedPage: page }) => {
  await createTx(page.request, { ...BANK_DEPOSIT, to_account_id: 3 });
  await openAddForm(page, "Transfer");
  await page.getByLabel("From Account").selectOption("Exchange USD");
  await expect(page.getByLabel("To Account")).toHaveValue("Bank");
  await page.getByLabel("Amount (From)").fill("500");
  await page.getByLabel("Amount (To)").fill("505");
  await expect(page.getByLabel("Fee (USD)")).toHaveValue("0");
  await page.getByRole("button", { name: "Save Transaction" }).click();
  await expect(page.getByText("Amount (To) can't be more than Amount (From)")).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(1);

  // Fixing what left clears it: the check follows Amount (From) too
  await page.getByLabel("Amount (From)").fill("505.50");
  await expect(page.getByText("Amount (To) can't be more than Amount (From)")).toHaveCount(0);
  await expect(page.getByLabel("Fee (USD)")).toHaveValue("0.5");
  await saveForm(page);
  const by = await balances(page);
  expect([by["Exchange USD"], by["Bank"], by["USD Fees"]]).toEqual([1494.5, 505, 0.5]);
});
