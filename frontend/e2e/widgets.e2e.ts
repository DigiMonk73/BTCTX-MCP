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

test("converter, date mode: the day's price", async ({ authedPage: page }) => {
  await page.getByRole("button", { name: "Date" }).click();
  await page.getByLabel("Select Date").fill("2024-03-01");
  await expect(page.getByText(/\$50,000\.00/)).toBeVisible();
  await page.getByLabel("BTC", { exact: true }).fill("1");
  await expect(page.getByLabel("USD", { exact: true })).toHaveValue("50000");
});
