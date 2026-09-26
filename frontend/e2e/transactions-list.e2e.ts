// The Transactions list: order, sort, pagination, day groups, and what each
// row shows.
import { test, expect, createTx, seedKnownLedger } from "./fixtures";
import type { Page } from "@playwright/test";

async function rowTypes(page: Page) {
  return (await page.getByRole("listitem").all()).map(async (r) =>
    (await r.innerText()).match(/\b(Deposit|Withdrawal|Transfer|Buy|Sell)\b/)?.[1],
  );
}

async function types(page: Page) {
  return Promise.all(await rowTypes(page));
}

test("empty state", async ({ authedPage: page }) => {
  await page.getByRole("link", { name: "Transactions" }).click();
  await expect(page.getByText("No transactions found.")).toBeVisible();
});

test("newest first by date; Last Added sorts by entry order", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  // Entered last, dated first.
  await createTx(page.request, {
    type: "Deposit", timestamp: "2022-12-01T15:00:00Z", from_account_id: 99, to_account_id: 1,
    amount: "10", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  await page.getByRole("link", { name: "Transactions" }).click();
  await expect(page.getByRole("listitem")).toHaveCount(7);
  expect(await types(page)).toEqual(["Sell", "Deposit", "Transfer", "Sell", "Buy", "Deposit", "Deposit"]);

  await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
  expect(await types(page)).toEqual(["Deposit", "Sell", "Deposit", "Transfer", "Sell", "Buy", "Deposit"]);
});

test("rows show account, amounts, fee, source and gain", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await page.getByRole("link", { name: "Transactions" }).click();
  const rows = page.getByRole("listitem");

  const sell1 = rows.filter({ hasText: "Sell" }).filter({ hasText: /0\.25000000 BTC/ });
  await expect(sell1).toContainText("Exchange");
  await expect(sell1).toContainText(/0\.25000000 BTC -> \$6,?980\.00/);
  await expect(sell1).toContainText(/Fee: \$20\.00/);
  await expect(sell1).toContainText(/Gain: \+\$1,?980\.00 \(\+39\.60%\) \(SHORT\)/);

  const sell2 = rows.filter({ hasText: "Sell" }).filter({ hasText: /0\.10000000 BTC/ });
  await expect(sell2).toContainText(/Gain: \+\$7,?000\.00 \(\+350\.00%\) \(LONG\)/);

  const transfer = rows.filter({ hasText: "Transfer" });
  await expect(transfer).toContainText("Exchange -> Wallet");
  await expect(transfer).toContainText("0.50000000 BTC");
  await expect(transfer).toContainText("Fee: 0.00010000 BTC");

  const income = rows.filter({ hasText: "Income" });
  await expect(income).toContainText("Wallet");
  await expect(income).toContainText("0.01000000 BTC");

  const buy = rows.filter({ hasText: "Buy" });
  await expect(buy).toContainText(/\$20,?000\.00 -> 1\.00000000 BTC/);
});

test("rows are grouped by the local day, with local times", async ({ authedPage: page }, info) => {
  // 03:04 UTC on June 15: June 14 in Chicago, June 15 in Tokyo.
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-06-15T03:04:05Z", from_account_id: 99, to_account_id: 1,
    amount: "10", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  await page.getByRole("link", { name: "Transactions" }).click();
  const tokyo = info.project.use.timezoneId === "Asia/Tokyo";
  const day = page.getByRole("list", { name: tokyo ? "Jun 15, 2024" : "Jun 14, 2024" });
  await expect(day.getByRole("listitem")).toContainText(tokyo ? "12:04 PM" : "10:04 PM");
});

test("pagination and items per page", async ({ authedPage: page }) => {
  for (let i = 1; i <= 12; i++) {
    await createTx(page.request, {
      type: "Deposit", timestamp: `2024-01-${String(i).padStart(2, "0")}T15:00:00Z`,
      from_account_id: 99, to_account_id: 1, amount: String(i), fee_amount: "0",
      fee_currency: "USD", source: "N/A",
    });
  }
  await page.getByRole("link", { name: "Transactions" }).click();
  await expect(page.getByRole("listitem")).toHaveCount(10);
  await expect(page.getByText("Page 1 of 2")).toBeVisible();
  await expect(page.getByRole("button", { name: "« Prev" })).toBeDisabled();

  await page.getByRole("button", { name: "Next »" }).click();
  await expect(page.getByText("Page 2 of 2")).toBeVisible();
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("button", { name: "Next »" })).toBeDisabled();

  await page.getByLabel("Items per page").selectOption("25");
  await expect(page.getByText("Page 1 of 1")).toBeVisible();
  await expect(page.getByRole("listitem")).toHaveCount(12);
});
