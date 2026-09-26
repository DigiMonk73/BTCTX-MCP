// Dashboard figures after a known ledger (seedKnownLedger), worked by hand:
//   Bank: 100,000 − 20,000 (buy) = 80,000
//   Exchange USD: 7,000 − 20 fee (sell 1) + 9,000 (sell 2) = 15,980
//   Exchange BTC: 1 − 0.25 − 0.5 − 0.1 = 0.15
//   Wallet: 0.5 − 0.0001 fee + 0.01 income = 0.5099
//   Basis left: 0.15 × 20,000 + 0.4999 × 20,000 + 500 = 13,498
//   Unrealized at $60,000: 0.6599 × 60,000 − 13,498 = 26,096
//   Short-term: sell 1 7,000 − 20 − 5,000 = 1,980; the transfer fee
//     0.0001 BTC at $50,000 = $5 proceeds − $2 basis = 3  → 1,983
//   Long-term: sell 2 (held > 1 year) 9,000 − 2,000 = 7,000
//   Income: 0.01 BTC at $50,000 = 500
import { test, expect, figure, seedKnownLedger, CURRENT_PRICE } from "./fixtures";

test("empty ledger shows zeros", async ({ authedPage: page }) => {
  await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
  expect(await figure(page, "Bank (USD)")).toBe(0);
  expect(await figure(page, "Total BTC")).toBe(0);
  expect(await figure(page, "Total Net Capital Gains")).toBe(0);
});

test("balances, basis, gains and income after a known ledger", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await page.reload();

  expect(await figure(page, "Bank (USD)")).toBe(80000);
  expect(await figure(page, "Exchange (USD)")).toBe(15980);
  expect(await figure(page, "Exchange (BTC)")).toBe(0.15);
  expect(await figure(page, "Wallet (BTC)")).toBe(0.5099);
  expect(await figure(page, "Total BTC")).toBe(0.6599);
  expect(await figure(page, "BTC Cost Basis")).toBeCloseTo(13498 / 0.6599, 1);
  expect(await figure(page, "Unrealized Gains/Losses")).toBeCloseTo(26096, 0);

  expect(await figure(page, "Short-Term Gains")).toBe(1983);
  expect(await figure(page, "Short-Term Losses")).toBe(0);
  expect(await figure(page, "Net Short-Term")).toBe(1983);
  expect(await figure(page, "Long-Term Gains")).toBe(7000);
  expect(await figure(page, "Net Long-Term")).toBe(7000);
  expect(await figure(page, "Total Net Capital Gains")).toBe(8983);

  expect(await figure(page, "Income")).toBe(500);
  expect(await figure(page, "Total Income")).toBe(500);
  expect(await figure(page, "Fees (USD)")).toBe(20);
  expect(await figure(page, "Fees (BTC)")).toBe(0.0001);
});

test("current price and block height", async ({ authedPage: page }) => {
  await expect(page.getByRole("heading", { name: "Current Bitcoin Price" })).toBeVisible();
  await expect(page.getByText(/\$60,?000\.00/).first()).toBeVisible();
  await expect(page.getByText(/Block Height: 900,?000/)).toBeVisible();
  expect(CURRENT_PRICE).toBe(60000);
});
