// Screenshots of every page for design review. Not part of the test suite;
// run with e2e/shots/screenshots.config.ts (SHOTS_DIR picks the folder).
import path from "node:path";
import type { Page } from "@playwright/test";
import {
  test, expect, seedKnownLedger, createTx, openAddForm, claimAccount, loginViaUi,
} from "../fixtures";

const OUT = process.env.SHOTS_DIR ?? path.resolve("shots-out");
const SIZES = [
  { name: "1280", width: 1280, height: 800 },
  { name: "800", width: 800, height: 600 },
  { name: "390", width: 390, height: 844 },
];

const RIVER_CSV = [
  "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag",
  "2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy",
  "2026-02-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell",
  "2026-02-01 09:00:00,,,0.00002000,BTC,,,Interest",
  "2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,",
].join("\n") + "\n";

for (const size of SIZES) {
  test(`pages at ${size.name}`, async ({ page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    const shot = async (name: string) => {
      await page.mouse.move(0, size.height - 1); // no hover state in the shot
      await page.waitForLoadState("networkidle");
      await page.screenshot({ path: path.join(OUT, `${name}-${size.name}.png`), animations: "disabled" });
    };

    // Before an account is claimed: the register page.
    await page.goto("/register");
    await expect(page.getByRole("button", { name: "Register" })).toBeVisible();
    await shot("register");

    await claimAccount(page.request);
    await page.goto("/login");
    await expect(page.getByRole("button", { name: "Log In" })).toBeVisible();
    await shot("login");

    await loginViaUi(page);
    await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
    await shot("dashboard-empty");

    await page.getByRole("link", { name: "Transactions" }).click();
    await expect(page.getByText(/Loading transactions/i)).toHaveCount(0);
    await shot("transactions-empty");

    await seedKnownLedger(page.request);
    await createTx(page.request, {
      type: "Withdrawal", timestamp: "2025-05-10T16:30:00Z", from_account_id: 2, to_account_id: 99,
      amount: "0.01", purpose: "Spent", gross_proceeds_usd: "950", fee_amount: "0.00002", fee_currency: "BTC",
    });
    await createTx(page.request, {
      type: "Buy", timestamp: "2025-08-02T14:00:00Z", from_account_id: 3, to_account_id: 4,
      amount: "0.02", cost_basis_usd: "2300", fee_amount: "5", fee_currency: "USD",
    });

    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
    await expect(page.locator(".btc-price-value")).toContainText("60,000");
    await shot("dashboard");

    await page.getByRole("link", { name: "Transactions" }).click();
    await expect(page.getByText(/Loading transactions/i)).toHaveCount(0);
    await expect(page.getByRole("listitem").first()).toBeVisible();
    await shot("transactions");

    await openAddForm(page, "Withdrawal");
    await shot("form");
    await page.keyboard.press("Escape");

    await page.goto("/transactions");
    await page.getByRole("listitem").filter({ hasText: "Transfer" }).getByRole("button", { name: "Edit" }).click();
    await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
    await expect(page.getByLabel("Amount").first()).not.toHaveValue("");
    await shot("form-edit");

    await page.goto("/reports");
    await expect(page.getByRole("heading", { name: "Reports" })).toBeVisible();
    await shot("reports");

    await page.goto("/settings");
    await shot("settings");
    await scrollTo(page, /Privacy/);
    await shot("settings-privacy");

    const river = page.getByRole("region", { name: "Import from River" });
    await river.getByLabel("River CSV file").setInputFiles({
      name: "river.csv", mimeType: "text/csv", buffer: Buffer.from(RIVER_CSV),
    });
    await river.getByRole("button", { name: "Preview" }).click();
    await expect(river.getByText("4 rows in file")).toBeVisible();
    await river.scrollIntoViewIfNeeded();
    await shot("settings-river");
  });
}

async function scrollTo(page: Page, name: RegExp) {
  const region = page.getByRole("region", { name });
  await region.first().evaluate((el) => el.scrollIntoView({ block: "start" }));
}
