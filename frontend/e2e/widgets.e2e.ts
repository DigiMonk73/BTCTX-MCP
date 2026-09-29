// Sidebar widgets: the calculator and the sats converter.
import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

async function press(page: Page, keys: string) {
  for (const k of keys) await page.getByRole("button", { name: k, exact: true }).click();
}

test("calculator: + − × ÷ and clear", async ({ authedPage: page }) => {
  const display = page.getByRole("status", { name: "Calculator display" });
  await expect(display).toHaveText("0");
  await press(page, "12+30=");
  await expect(display).toHaveText("42");
  await press(page, "C");
  await expect(display).toHaveText("0");
  await press(page, "7*6=");
  await expect(display).toHaveText("42");
  await press(page, "C9-12=");
  await expect(display).toHaveText("-3");
  await press(page, "C1/4=");
  await expect(display).toHaveText("0.25");
  await press(page, "C2.5*2=");
  await expect(display).toHaveText("5");
});

test("converter, auto mode: live price", async ({ authedPage: page }) => {
  await expect(page.getByRole("button", { name: "Auto" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("BTC Price: $60,000.00")).toBeVisible();
  await page.getByLabel("USD", { exact: true }).fill("600");
  await expect(page.getByLabel("BTC", { exact: true })).toHaveValue("0.01");
  await expect(page.getByLabel("Sats", { exact: true })).toHaveValue("1000000");

  await page.getByLabel("Sats", { exact: true }).fill("250000");
  await expect(page.getByLabel("BTC", { exact: true })).toHaveValue("0.0025");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("150");

  await page.getByLabel("BTC", { exact: true }).fill("0.5");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("30000");
  await expect(page.getByLabel("Sats", { exact: true })).toHaveValue("50000000");
});

test("the calculator stays put in every converter mode and ends level with the cards", async ({ authedPage: page }) => {
  // Owner's request 2026-09-29: the calculator looked scrunched and ended
  // short of the Realized Gains/Losses card; it also jumped when the
  // converter's mode changed (Auto's price line is shorter than Manual's field).
  await page.setViewportSize({ width: 1440, height: 900 });
  const calculator = page.getByRole("status", { name: "Calculator display" }).locator("xpath=..");
  const edges = async () => {
    const box = (await calculator.boundingBox())!;
    return [Math.round(box.y), Math.round(box.y + box.height)];
  };
  const auto = await edges();
  await page.getByRole("button", { name: "Manual" }).click();
  expect(await edges()).toEqual(auto);
  await page.getByRole("button", { name: "Date" }).click();
  expect(await edges()).toEqual(auto);
  await page.getByLabel("Select Date").fill("2024-03-01");
  await expect(page.getByText(/\$50,000\.00/)).toBeVisible();
  expect(await edges()).toEqual(auto);

  const realized = page.locator(".card, section, div").filter({
    has: page.getByRole("heading", { name: "Realized Gains/Losses (FIFO)", exact: true }),
  }).last();
  const card = (await realized.boundingBox())!;
  // The cards' height follows the page width (the Income & Fees card's text
  // wraps), so level to within a couple of pixels
  expect(Math.abs(auto[1] - Math.round(card.y + card.height))).toBeLessThanOrEqual(3);
});

test("converter with prices off says so, never $0.00", async ({ authedPage: page }) => {
  // VM test 2026-09-29 (F2): it read "BTC Price: $0.00" and kept old USD figures.
  const off = { price_source: "off", mempool_url: null, mempool_fallback: false, proxy_url: null };
  const r = await page.request.put("/api/settings/network", { data: off });
  expect(r.ok(), await r.text()).toBeTruthy();
  await page.reload();
  await expect(page.getByText("BTC Price: Prices off")).toBeVisible();
  await expect(page.getByText(/BTC Price: \$/)).toHaveCount(0);
  await page.getByLabel("BTC", { exact: true }).fill("0.5");
  await expect(page.getByLabel("Sats", { exact: true })).toHaveValue("50000000");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("");
});

test("converter keeps BTC to the satoshi (F6)", async ({ authedPage: page }) => {
  // $1 at $60,000 = 0.0000166666… BTC; it used to show 0.00002 (5 decimals).
  await page.getByLabel("USD", { exact: true }).fill("1");
  await expect(page.getByLabel("BTC", { exact: true })).toHaveValue("0.00001667");
  await expect(page.getByLabel("Sats", { exact: true })).toHaveValue("1666");
  await page.getByLabel("Sats", { exact: true }).fill("1");
  await expect(page.getByLabel("BTC", { exact: true })).toHaveValue("0.00000001");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("0");
});

test("converter, manual mode: your own price", async ({ authedPage: page }) => {
  await page.getByRole("button", { name: "Manual" }).click();
  await expect(page.getByRole("button", { name: "Manual" })).toHaveAttribute("aria-pressed", "true");
  const price = page.getByLabel("BTC Price (USD)");
  await expect(price).toHaveValue("60000");
  await page.getByLabel("BTC", { exact: true }).fill("2");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("120000");
  await price.fill("100000");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("200000");
});

test("converter, manual mode: a slow price answer never overwrites the price you typed", async ({ authedPage: page }) => {
  // Switching to Manual asks for a starting price; on a busy server it
  // arrived after the owner had typed theirs, and replaced it.
  await expect(page.getByLabel("USD", { exact: true })).toBeVisible();
  await page.route("**/api/bitcoin/price", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 1500));
    await route.fulfill({ status: 200, contentType: "application/json", body: '{"USD": 70000}' });
  });
  await page.getByRole("button", { name: "Manual" }).click();
  await page.getByLabel("BTC", { exact: true }).fill("2");
  await page.getByLabel("BTC Price (USD)").fill("100000");
  await page.waitForTimeout(2500); // the slow answer has come and gone
  await expect(page.getByLabel("BTC Price (USD)")).toHaveValue("100000");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("200000");
});

test("converter, date mode: the day's price", async ({ authedPage: page }) => {
  await page.getByRole("button", { name: "Date" }).click();
  await page.getByLabel("Select Date").fill("2024-03-01");
  await expect(page.getByText(/\$50,000\.00/)).toBeVisible();
  await page.getByLabel("BTC", { exact: true }).fill("1");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("50000");
});
