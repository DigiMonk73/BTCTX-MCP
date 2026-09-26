import path from "node:path";
import { test, expect, seedKnownLedger, createTx, openAddForm } from "../fixtures";

const OUT = process.env.SHOTS_DIR ?? path.resolve("shots-out");
const SIZES = [
  { name: "1280", width: 1280, height: 800 },
  { name: "800", width: 800, height: 600 },
];

for (const size of SIZES) {
  test(`pages at ${size.name}`, async ({ authedPage: page }) => {
    await page.setViewportSize({ width: size.width, height: size.height });
    await seedKnownLedger(page.request);
    // A few recent rows so the list shows each kind of transaction.
    await createTx(page.request, {
      type: "Withdrawal", timestamp: "2025-05-10T16:30:00Z", from_account_id: 2, to_account_id: 99,
      amount: "0.01", purpose: "Spent", gross_proceeds_usd: "950", fee_amount: "0.00002", fee_currency: "BTC",
    });
    await createTx(page.request, {
      type: "Buy", timestamp: "2025-08-02T14:00:00Z", from_account_id: 3, to_account_id: 4,
      amount: "0.02", cost_basis_usd: "2300", fee_amount: "5", fee_currency: "USD",
    });
    const shot = async (name: string, fullPage = false) => {
      await page.mouse.move(0, size.height - 1); // no hover state in the shot
      await page.screenshot({ path: path.join(OUT, `${name}-${size.name}.png`), fullPage, animations: "disabled" });
    };

    await page.reload();
    await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
    await page.waitForLoadState("networkidle");
    await shot("dashboard");

    await page.getByRole("link", { name: "Transactions" }).click();
    await expect(page.getByText("Loading transactions")).toHaveCount(0);
    await page.waitForLoadState("networkidle");
    await shot("transactions");

    await openAddForm(page, "Withdrawal");
    await page.waitForLoadState("networkidle");
    await shot("form");
    await page.keyboard.press("Escape");

    await page.goto("/settings");
    await page.waitForLoadState("networkidle");
    await shot("settings");
    const net = page.getByRole("region", { name: /Privacy/ });
    if (await net.count()) {
      await net.first().scrollIntoViewIfNeeded();
      await shot("settings-privacy");
    }
  });
}
