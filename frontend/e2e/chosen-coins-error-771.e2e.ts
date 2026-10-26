// When the coins chosen don't add up to what leaves, Save's refusal is seen
// (#771): the panel scrolls to it, beside the picker's total, focus moves to
// it, and it's announced (role "alert"), on a desktop panel and a phone's.
// Before, it showed far below the part of the panel on screen, so Save
// seemed to do nothing.
import { test, expect, createTx, openAddForm } from "./fixtures";
import type { Page } from "@playwright/test";

const DOESNT_ADD_UP = "The coins chosen must add up to what leaves: choose coins for all of it, or don't choose them.";

/** A Spent of 0.1 BTC (a 0.0001 fee) from Wallet, which holds 0.3 BTC acquired in 2017, choosing 0.2 of them. */
async function aChoiceThatDoesntAddUp(page: Page) {
  await createTx(page.request, {
    type: "Deposit", timestamp: "2023-01-10T12:00:00Z", from_account_id: 99, to_account_id: 2, amount: "0.3",
    fee_amount: "0", fee_currency: "BTC", source: "MyBTC", cost_basis_usd: "300", acquired_at: "2017-03-01",
  });
  await openAddForm(page, "Withdrawal");
  await page.getByLabel("Date & Time").fill("2026-03-01T10:15:30");
  await page.getByLabel("Account", { exact: true }).selectOption("Wallet");
  await page.getByLabel("Amount", { exact: true }).fill("0.1");
  await page.getByLabel("Purpose (BTC only)").selectOption("Spent");
  await page.getByLabel("Fee (BTC)").fill("0.0001");
  await page.getByLabel("Proceeds (USD)").fill("10000");
  await page.getByRole("button", { name: "Choose which coins leave" }).click();
  await page.getByLabel("BTC chosen from the coins acquired Mar 1, 2017").fill("0.2");
  await expect(page.getByText(
    "Chosen 0.20000000 of 0.10010000 BTC: the amount 0.10000000 and the network fee 0.00010000.")).toBeVisible();
}

async function saveIsRefusedInSight(page: Page) {
  await page.getByLabel("Date & Time").scrollIntoViewIfNeeded();  // back to the top of the panel, as the owner would
  await expect(page.getByText(DOESNT_ADD_UP)).toHaveCount(0);
  await page.getByRole("button", { name: "Save transaction" }).click();
  const refusal = page.getByRole("alert").filter({ hasText: DOESNT_ADD_UP });
  await expect(refusal).toBeInViewport({ ratio: 1 });
  await expect(refusal).toBeFocused();
  expect((await (await page.request.get("/api/transactions")).json()).map((tx: { type: string }) => tx.type))
    .toEqual(["Deposit"]);
}

test("on a desktop panel, Save's refusal of coins that don't add up is in sight and announced", async (
  { authedPage: page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await aChoiceThatDoesntAddUp(page);
  await saveIsRefusedInSight(page);
});

test("on a phone's panel, Save's refusal of coins that don't add up is in sight and announced", async (
  { authedPage: page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await aChoiceThatDoesntAddUp(page);
  await saveIsRefusedInSight(page);
});
