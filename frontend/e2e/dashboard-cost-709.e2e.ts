// Each account's own cost on Portfolio Overview (#709): an opened Wallet
// (BTC) or Exchange (BTC) line shows each account's cost basis, the
// server's figure, beside its amount, and on a phone too; the card's
// totals stay as they are. Elements by role and name.
import { test, expect, createTx, seedKnownLedger } from "./fixtures";
import type { Page } from "@playwright/test";

const overview = (page: Page) => page.locator(".portfolio-overview");
const usd = (n: number) => `$${n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

/** Each account's cost basis as the server gives it, by id. */
async function costs(page: Page): Promise<Map<number, number | null>> {
  const rows: { account_id: number; cost_basis: number | null }[] = await (await page.request.get("/api/calculations/accounts/balances")).json();
  return new Map(rows.map((r) => [r.account_id, r.cost_basis]));
}

async function twoWallets(page: Page) {
  await seedKnownLedger(page.request);
  const r = await page.request.post("/api/accounts/", { data: { kind: "wallet", name: "Coldcard" } });
  expect(r.status(), await r.text()).toBe(201);
  // Half the wallet's coins to the Coldcard (id 100): their cost goes with them
  await createTx(page.request, { type: "Transfer", timestamp: "2024-04-01T15:00:00Z", from_account_id: 2,
    to_account_id: 100, amount: "0.25", fee_amount: "0.0001", fee_currency: "BTC" });
  await page.reload();
}

test("an opened Wallet (BTC) line shows each wallet's cost basis, the server's", async ({ authedPage: page }) => {
  await twoWallets(page);
  const cost = await costs(page);
  expect(cost.get(2)).toBeGreaterThan(0);
  expect(cost.get(100)).toBeGreaterThan(0);
  expect(cost.get(1)).toBeNull(); // the bank's dollars have none
  // The card's totals once loaded, the price's gain too
  const totalLines = overview(page).locator("hr ~ p");
  await expect(totalLines).toHaveCount(3);
  await expect(totalLines.last()).not.toContainText("Loading");
  const totals = await totalLines.allTextContents();

  await overview(page).getByRole("button", { name: /^Wallet \(BTC\)/ }).click();
  const items = overview(page).getByRole("list", { name: "Wallet (BTC) accounts" }).getByRole("listitem");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0).locator(".balance-line-cost")).toContainText(`Cost basis ${usd(cost.get(2)!)}`);
  await expect(items.nth(1).locator(".balance-line-cost")).toContainText(`Cost basis ${usd(cost.get(100)!)}`);
  await expect(totalLines).toHaveText(totals);
});

test("on a phone each account's cost sits under its amount, inside the card", async ({ authedPage: page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await twoWallets(page);
  await overview(page).getByRole("button", { name: /^Wallet \(BTC\)/ }).click();
  const item = overview(page).getByRole("list", { name: "Wallet (BTC) accounts" }).getByRole("listitem").nth(1);
  const [amount, cost, card] = [await item.locator(".balance-line-amount").boundingBox(),
    await item.locator(".balance-line-cost").boundingBox(), await overview(page).boundingBox()];
  expect(cost!.y).toBeGreaterThanOrEqual(amount!.y + amount!.height - 1);
  expect(cost!.x + cost!.width).toBeLessThanOrEqual(card!.x + card!.width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
});
