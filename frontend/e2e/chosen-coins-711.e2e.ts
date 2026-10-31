// Choosing which coins leave a wallet (#711, step C3), from the real server:
// a Spent and a Transfer out of Wallet choose newer coins than the oldest,
// save, open again on their choice, an edit of the amount chooses again,
// and "Don't choose coins" goes back to oldest first. On a transaction in an
// earlier tax year the past-year question says when a choice counts. At
// phone width each purchase is a card.
import { test, expect, createTx, openAddForm, saveForm, SAVE_ANYWAY } from "./fixtures";
import type { Page } from "@playwright/test";

const RULE = /^Choose coins only if you decided which coins to send by the time they left/;
const OLD = "BTC chosen from the coins acquired Mar 1, 2017";
const NEW = "BTC chosen from the coins acquired Jan 15, 2025";

/** Wallet holds 0.3 BTC acquired 2017 for $300 and 0.5 BTC deposited 2025-01-15 for $45,000. Their ids. */
async function walletWithTwoPurchases(page: Page): Promise<{ old: number; recent: number }> {
  expect((await page.request.post("/api/accounts/", { data: { kind: "wallet", name: "Cold Storage" } })).status())
    .toBe(201);
  const old = await createTx(page.request, {
    type: "Deposit", timestamp: "2023-01-10T12:00:00Z", from_account_id: 99, to_account_id: 2, amount: "0.3",
    fee_amount: "0", fee_currency: "BTC", source: "MyBTC", cost_basis_usd: "300", acquired_at: "2017-03-01",
  });
  const recent = await createTx(page.request, {
    type: "Deposit", timestamp: "2025-01-15T12:00:00Z", from_account_id: 99, to_account_id: 2, amount: "0.5",
    fee_amount: "0", fee_currency: "BTC", source: "MyBTC", cost_basis_usd: "45000",
  });
  return { old: old.id, recent: recent.id };
}

async function saved(page: Page, type: string): Promise<{ id: number; chosen_coins: unknown }> {
  const all = await (await page.request.get("/api/transactions")).json();
  return all.find((tx: { type: string }) => tx.type === type);
}

async function openSaved(page: Page, title: string) {
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").filter({ hasText: title }).getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
}

async function newSpent(page: Page, when: string) {
  await openAddForm(page, "Withdrawal");
  await page.getByLabel("Date & Time").fill(when);
  await page.getByLabel("Account", { exact: true }).selectOption("Wallet");
  await page.getByLabel("Amount", { exact: true }).fill("0.1");
  await page.getByLabel("Purpose (BTC only)").selectOption("Spent");
  await page.getByLabel("Fee (BTC)").fill("0.0001");
  await page.getByLabel("Proceeds (USD)").fill("10000");
}

test("a Spent chooses newer coins, opens on them, and chooses again after its amount changes", async (
  { authedPage: page }) => {
  const ids = await walletWithTwoPurchases(page);
  await newSpent(page, "2026-03-01T10:15:30");
  const leaving = page.getByRole("table", { name: "Coins that will leave" });
  await expect(leaving.locator("tbody tr").first().locator("td").first()).toHaveText("Mar 1, 2017");

  await page.getByRole("button", { name: "Choose which coins leave" }).click();
  await expect(page.getByText(RULE)).toBeVisible();
  await expect(page.getByLabel(OLD)).toHaveValue("0.1001");
  await page.getByLabel(OLD).fill("");
  await page.getByLabel(NEW).fill("0.1001");
  await expect(page.getByText(
    "Chosen 0.10010000 of 0.10010000 BTC: the amount 0.10000000 and the network fee 0.00010000.")).toBeVisible();
  await expect(leaving.locator("tbody tr").first().locator("td").first()).toHaveText("Jan 15, 2025");
  await saveForm(page);
  expect((await saved(page, "Withdrawal")).chosen_coins).toEqual([{ acquired_txn_id: ids.recent, btc: "0.10010000" }]);

  // Opened again on its choice; a new amount no longer adds up, and Save waits
  await openSaved(page, "Withdrawal");
  await expect(page.getByLabel(NEW)).toHaveValue("0.1001");
  await page.getByLabel("Amount", { exact: true }).fill("0.2");
  await expect(page.getByText(
    "Chosen 0.10010000 of 0.20010000 BTC: the amount 0.20000000 and the network fee 0.00010000.")).toBeVisible();
  await page.getByRole("button", { name: "Update Transaction" }).click();
  await expect(page.getByText("The coins chosen must add up to what leaves: choose coins for all of it, or don't " +
    "choose them.")).toBeVisible();
  await page.getByLabel(NEW).fill("0.2001");
  await saveForm(page, "Update Transaction");
  expect((await saved(page, "Withdrawal")).chosen_coins).toEqual([{ acquired_txn_id: ids.recent, btc: "0.20010000" }]);

  // Back to oldest first
  await openSaved(page, "Withdrawal");
  await page.getByRole("button", { name: "Don't choose coins" }).click();
  await expect(page.getByText(RULE)).toHaveCount(0);
  await saveForm(page, "Update Transaction");
  expect((await saved(page, "Withdrawal")).chosen_coins).toBeNull();
});

test("a Transfer to another wallet moves the coins it chose", async ({ authedPage: page }) => {
  const ids = await walletWithTwoPurchases(page);
  await openAddForm(page, "Transfer");
  await page.getByLabel("Date & Time").fill("2026-03-01T10:15:30");
  await page.getByLabel("From Account").selectOption("Wallet");
  await page.getByLabel("To Account").selectOption("Cold Storage");
  await page.getByLabel("Amount (From)").fill("0.2001");
  await page.getByLabel("Amount (To)").fill("0.2");
  await page.getByRole("button", { name: "Choose which coins leave" }).click();
  await page.getByLabel(OLD).fill("");
  await page.getByLabel(NEW).fill("0.2001");
  await expect(page.getByText(
    "Chosen 0.20010000 of 0.20010000 BTC: Amount (To) 0.20000000 and the network fee 0.00010000.")).toBeVisible();
  await saveForm(page);
  expect((await saved(page, "Transfer")).chosen_coins).toEqual([{ acquired_txn_id: ids.recent, btc: "0.20010000" }]);

  await openSaved(page, "Transfer");
  const moved = page.getByRole("table", { name: "Coins that will move" });
  await expect(moved.locator("tbody tr")).toHaveCount(1);
  await expect(moved.locator("tbody tr").first().locator("td")).toHaveText(["Jan 15, 2025", "0.20000000", "$18,000.00"]);
});

test("a choice on a transaction in an earlier tax year: the question says when it counts", async (
  { authedPage: page }) => {
  const ids = await walletWithTwoPurchases(page);
  await createTx(page.request, {
    type: "Withdrawal", timestamp: "2025-06-01T12:00:00Z", from_account_id: 2, to_account_id: 99, amount: "0.1",
    fee_amount: "0", fee_currency: "BTC", purpose: "Spent", proceeds_usd: "10000",
  });
  await openSaved(page, "Withdrawal");
  await page.getByRole("button", { name: "Choose which coins leave" }).click();
  await expect(page.getByText(/after the coins left on Jun 1, 2025\. A choice counts only if you made it by then/))
    .toBeVisible();
  await page.getByLabel(OLD).fill("");
  await page.getByLabel(NEW).fill("0.1");
  await page.getByRole("button", { name: "Update Transaction" }).click();
  const dialog = page.getByRole("dialog", { name: "Change an earlier tax year?" });
  await expect(dialog.getByText(
    "A choice of coins counts only if you made it by the time they left and your records show it.")).toBeVisible();
  await dialog.getByRole("button", { name: SAVE_ANYWAY }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toHaveCount(0);
  expect((await saved(page, "Withdrawal")).chosen_coins).toEqual([{ acquired_txn_id: ids.recent, btc: "0.10000000" }]);
});

test("at phone width, each purchase is a card", async ({ authedPage: page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await walletWithTwoPurchases(page);
  await newSpent(page, "2026-03-01T10:15:30");
  await page.getByRole("button", { name: "Choose which coins leave" }).click();
  const table = page.getByRole("table", { name: "Coins in Wallet then" });
  await expect(table.locator("tbody tr")).toHaveCount(2);
  const row = table.locator("tbody tr").first();
  expect(await row.evaluate((el) => getComputedStyle(el).display)).toBe("block");
  expect(await table.locator("thead").evaluate((el) => getComputedStyle(el).display)).toBe("none");
  await expect(page.getByLabel(NEW)).toBeVisible();
  const box = await page.getByLabel(NEW).boundingBox();
  expect(box && box.x + box.width).toBeLessThanOrEqual(390);
});
