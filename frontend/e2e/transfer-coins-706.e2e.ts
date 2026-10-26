// The Transfer form lists the coins that will move before it saves (#706;
// the owner's decision, 2026-10-25), from the real server: the oldest coins
// in the From account first, each with its date acquired, amount and cost.
// The saved transfer, opened again, lists the same coins: the list is what
// the save did.
import { test, expect, createTx, openAddForm, saveForm } from "./fixtures";
import type { Page } from "@playwright/test";

const OLDEST_FIRST =
  "Per-wallet FIFO: your oldest coins in Wallet move first (the IRS default when you don't pick specific coins).";
const COINS = [
  ["Mar 1, 2017", "0.29990000", "$299.90"],
  ["May 1, 2024", "0.10010000", "$6,006.00"],
];

/** Wallet holds 0.3 BTC acquired in 2017 for $300 and 0.5 BTC acquired in 2024 for $30,000; Cold Storage is empty. */
async function twoWalletsAndTwoLots(page: Page) {
  expect((await page.request.post("/api/accounts/", { data: { kind: "wallet", name: "Cold Storage" } })).status())
    .toBe(201);
  for (const [when, amount, basis, acquired] of [
    ["2023-01-10T18:00:00Z", "0.3", "300", "2017-03-01"],
    ["2024-05-01T18:00:00Z", "0.5", "30000", "2024-05-01"],
  ]) {
    await createTx(page.request, {
      type: "Deposit", timestamp: when, from_account_id: 99, to_account_id: 2, amount, fee_amount: "0",
      fee_currency: "BTC", source: "MyBTC", cost_basis_usd: basis, acquired_at: acquired,
    });
  }
}

async function expectCoins(page: Page) {
  const coins = page.getByRole("table", { name: "Coins that will move" });
  await expect(coins.locator("tbody tr")).toHaveCount(COINS.length);
  for (const [i, cells] of COINS.entries()) {
    await expect(coins.locator("tbody tr").nth(i).locator("td")).toHaveText(cells);
  }
  await expect(page.getByText(/^The network fee, 0\.0001 BTC, is paid first, from your oldest coins/)).toBeVisible();
}

test("a transfer to another wallet lists the coins it moves, as its save moves them", async ({ authedPage: page }) => {
  await twoWalletsAndTwoLots(page);
  await openAddForm(page, "Transfer");
  await page.getByLabel("Date & Time").fill("2026-03-01T10:15:30");
  await page.getByLabel("From Account").selectOption("Wallet");
  await page.getByLabel("To Account").selectOption("Cold Storage");
  await expect(page.getByText(OLDEST_FIRST)).toBeVisible();
  await page.getByLabel("Amount (From)").fill("0.4001");
  await page.getByLabel("Amount (To)").fill("0.4");
  await expectCoins(page);
  await saveForm(page);

  const balances = await (await page.request.get("/api/calculations/accounts/balances")).json();
  const by = Object.fromEntries(balances.map((b: { name: string; balance: string }) => [b.name, Number(b.balance)]));
  expect(by["Cold Storage"]).toBe(0.4);

  // Opened again, the saved transfer lists the coins its save moved
  await page.getByRole("link", { name: "Transactions" }).click();
  const row = page.getByRole("listitem").filter({ hasText: "Transfer" });
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await expectCoins(page);
});
