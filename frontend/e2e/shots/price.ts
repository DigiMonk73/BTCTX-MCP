// The price card and where prices show (#145), for the pull requests' before
// and after: `PRICE_SHOTS_DIR=… npx playwright test -c e2e/shots/price.config.ts`.
// Throwaway data on the e2e server; not part of the test suite.
import path from "node:path";
import type { Page } from "@playwright/test";
import { test, expect, createTx, openSection, REPO } from "../fixtures";

const OUT = process.env.PRICE_SHOTS_DIR ?? path.join(REPO, "frontend", "test-results", "price-shots");

async function shot(page: Page, name: string, full = false) {
  await page.mouse.move(0, 0);
  await page.waitForLoadState("networkidle");
  await page.screenshot({ path: path.join(OUT, `${name}.png`), animations: "disabled", fullPage: full });
}

const settings = async (page: Page) => {
  await page.getByRole("link", { name: "Settings" }).click();
  const net = await openSection(page, "Privacy & Network");
  await net.scrollIntoViewIfNeeded();
  return net;
};

test.describe("first run", () => {
  test.use({ priceSource: "unset" });
  for (const [name, viewport] of [["desktop", { width: 1440, height: 900 }], ["phone", { width: 390, height: 844 }]] as const) {
    test(`first run, ${name}`, async ({ authedPage: page }) => {
      await page.setViewportSize(viewport);
      await expect(page.getByRole("region", { name: "Bitcoin prices" })).toBeVisible();
      await shot(page, `01-firstrun-${name}`, name === "phone");
    });
  }
});

test.describe("first run, the Mac app", () => {
  test.use({ priceSource: "unset", appMode: "mac", viewport: { width: 800, height: 600 } });
  test("first run, 800 × 600", async ({ authedPage: page }) => {
    await expect(page.getByRole("region", { name: "Bitcoin prices" })).toBeVisible();
    await shot(page, "02-firstrun-mac");
  });
});

test("settings: public, then your Mempool with its backup, then Nobody; the Dashboard; the sidebar", async ({
  authedPage: page,
}) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-06-15T03:04:05Z", from_account_id: 99, to_account_id: 2, amount: "0.1",
    fee_amount: "0", fee_currency: "BTC", source: "Income",
  });
  await expect(page.locator(".btc-price-value")).toHaveText(/^\$/);
  await shot(page, "03-dashboard-public");
  const net = await settings(page);
  await expect(net.getByRole("status")).toContainText("public price sites");
  await net.screenshot({ path: path.join(OUT, "04-settings-public.png") });
  await net.getByLabel(/^My own Mempool/).check();
  await net.getByLabel("Your Mempool's address").fill("http://umbrel.local:3006");
  await net.getByLabel("If it can't answer, ask public price sites").check();
  await net.getByLabel("Through Tor").check();
  await net.screenshot({ path: path.join(OUT, "05-settings-mempool-backup-tor.png") });
  await net.getByLabel(/^Nobody/).check();
  await net.getByRole("button", { name: "Save" }).click();
  await expect(net.getByRole("status")).toContainText("Fully offline");
  await net.screenshot({ path: path.join(OUT, "06-settings-nobody.png") });
  await page.getByRole("link", { name: "Dashboard" }).click();
  await page.goto("/dashboard");
  await expect(page.locator(".btc-price-value")).toHaveText("Offline");
  await shot(page, "07-dashboard-nobody");
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  await expect(page.locator(".field-origin")).toBeVisible();
  await shot(page, "08-form-from-the-price");
});

test.describe("set by StartOS", () => {
  test.use({ priceSource: "startos" });
  test("read-only", async ({ authedPage: page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const net = await settings(page);
    await net.screenshot({ path: path.join(OUT, "09-settings-startos.png") });
  });
});

test.describe("confirm once", () => {
  test.use({ priceSource: "unconfirmed", viewport: { width: 1440, height: 900 } });
  test("the confirm card", async ({ authedPage: page }) => {
    await expect(page.getByRole("region", { name: "Please confirm where BitcoinTX gets prices" })).toBeVisible();
    await shot(page, "10-confirm");
  });
});
