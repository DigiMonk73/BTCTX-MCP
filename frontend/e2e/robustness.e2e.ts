// What the UI does when things go wrong or slowly: double clicks, failed
// requests, a slow price service, a report that fails.
import { test, expect, listTx, openAddForm, seedFunds } from "./fixtures";

test("a double-clicked Save creates one transaction", async ({ authedPage: page }) => {
  // Hold the create request so the second click lands while the first is in flight.
  await page.route("**/api/transactions", async (route) => {
    if (route.request().method() === "POST") await new Promise((r) => setTimeout(r, 800));
    await route.continue();
  });
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill("2024-03-01T10:15:30");
  await page.getByLabel("Account").selectOption("Bank");
  await page.getByLabel("Amount").fill("100");
  // Two clicks as fast as a double-click; the button disables while saving.
  await page.getByRole("button", { name: "Save Transaction" }).dblclick();
  await expect(page.getByRole("heading", { name: "Add Transaction" })).toHaveCount(0);
  await page.unroute("**/api/transactions");
  expect(await listTx(page.request)).toHaveLength(1);
});

test("a refused save keeps the form open with its values and says why", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Sell");
  await page.getByLabel("Date & Time").fill("2024-03-01T10:15:30");
  await page.getByLabel("Amount BTC").fill("9");
  await page.getByLabel("Gross Proceeds (USD)").fill("1000");
  await page.getByRole("button", { name: "Save Transaction" }).click();
  await expect(page.getByText(/Failed to create transaction/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Add Transaction" })).toBeVisible();
  await expect(page.getByLabel("Amount BTC")).toHaveValue("9");
  await expect(page.getByRole("button", { name: "Save Transaction" })).toBeEnabled();
});

test("the transaction list says so when loading fails, and Retry works", async ({ authedPage: page }) => {
  let fail = true;
  await page.route("**/api/transactions", (route) =>
    fail && route.request().method() === "GET"
      ? route.fulfill({ status: 500, body: '{"detail":"boom"}', contentType: "application/json" })
      : route.continue(),
  );
  await page.getByRole("link", { name: "Transactions" }).click();
  await expect(page.getByText(/Failed to load transactions/)).toBeVisible();
  fail = false;
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("No transactions found.")).toBeVisible();
});

test("a slow price service doesn't block the dashboard", async ({ authedPage: page }) => {
  await page.route("**/api/bitcoin/price", async (route) => {
    await new Promise((r) => setTimeout(r, 2500));
    await route.continue();
  });
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
  await expect(page.getByText(/\$60,?000\.00/).first()).toBeVisible({ timeout: 10_000 });
});

test("an unreachable price service shows an error, not a crash", async ({ authedPage: page }) => {
  await page.route("**/api/bitcoin/**", (route) =>
    route.fulfill({ status: 502, body: '{"detail":"all sources failed"}', contentType: "application/json" }),
  );
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Current Bitcoin Price" })).toBeVisible();
});

test("a failed report says so", async ({ authedPage: page }) => {
  await page.route("**/api/reports/**", (route) =>
    route.fulfill({ status: 500, body: '{"detail":"boom"}', contentType: "application/json" }),
  );
  await page.getByRole("link", { name: "Reports" }).click();
  await page.getByLabel("Tax Year").selectOption("2024");
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByText("Failed to generate the report. Please try again.")).toBeVisible();
});
