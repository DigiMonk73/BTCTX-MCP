// Create every transaction type through the form and check what was saved.
import {
  test, expect, createTx, listTx, localToIso, openAddForm, saveForm, seedFunds,
  HISTORICAL_PRICE,
} from "./fixtures";
import type { Page } from "@playwright/test";

// Non-zero seconds: Chromium drops ":00" seconds from a datetime-local value.
const WHEN = "2024-03-01T10:15:30";

async function lastTx(page: Page) {
  const all = await listTx(page.request);
  return all.reduce((a, b) => ((a.id as number) > (b.id as number) ? a : b));
}

async function setWhen(page: Page, local = WHEN) {
  await page.getByLabel("Date & Time").fill(local);
}

test.describe("BTC deposits", () => {
  for (const source of ["MyBTC", "Gift", "N/A"]) {
    test(`deposit to Wallet, source ${source}, with a basis`, async ({ authedPage: page }) => {
      await openAddForm(page, "Deposit");
      await setWhen(page);
      await page.getByLabel("Account").selectOption("Wallet");
      await expect(page.getByLabel("Currency")).toHaveValue("BTC");
      await page.getByLabel("Amount").fill("0.25");
      await page.getByLabel("Source").selectOption(source);
      await page.getByLabel("Cost Basis (USD)").fill("7000");
      await saveForm(page);

      const tx = await lastTx(page);
      expect(tx).toMatchObject({
        type: "Deposit", from_account_id: 99, to_account_id: 2, source,
        timestamp: expect.any(String),
      });
      expect(Number(tx.amount)).toBe(0.25);
      expect(Number(tx.cost_basis_usd)).toBe(7000);
      expect(new Date(tx.timestamp as string).toISOString()).toBe(await localToIso(page, WHEN));
    });
  }

  for (const source of ["Income", "Interest", "Reward"]) {
    test(`deposit ${source} with a blank basis gets the day's value`, async ({ authedPage: page }) => {
      await openAddForm(page, "Deposit");
      await setWhen(page);
      await page.getByLabel("Account").selectOption("Exchange");
      await page.getByLabel("Currency").selectOption("BTC");
      await page.getByLabel("Amount").fill("0.01");
      await page.getByLabel("Source").selectOption(source);
      // Blank by default (it used to show 0).
      await expect(page.getByLabel("Cost Basis (USD)")).toHaveValue("");
      await saveForm(page);

      const tx = await lastTx(page);
      expect(tx).toMatchObject({ type: "Deposit", to_account_id: 4, source });
      expect(Number(tx.cost_basis_usd)).toBe(0.01 * HISTORICAL_PRICE);
    });
  }
});

test("USD deposit to the bank", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await setWhen(page);
  await page.getByLabel("Account").selectOption("Bank");
  await expect(page.getByLabel("Currency")).toHaveValue("USD");
  await expect(page.getByLabel("Source")).toHaveCount(0);
  await expect(page.getByLabel("Cost Basis (USD)")).toHaveCount(0);
  await page.getByLabel("Amount").fill("1234.56");
  await saveForm(page);
  const tx = await lastTx(page);
  expect(tx).toMatchObject({ type: "Deposit", from_account_id: 99, to_account_id: 1 });
  expect(Number(tx.amount)).toBe(1234.56);
});

test.describe("withdrawals", () => {
  test("Spent with proceeds is a disposal with a gain", async ({ authedPage: page }) => {
    await seedFunds(page.request);
    await openAddForm(page, "Withdrawal");
    await setWhen(page);
    await page.getByLabel("Account").selectOption("Exchange");
    await page.getByLabel("Currency").selectOption("BTC");
    await page.getByLabel("Amount").fill("0.1");
    await page.getByLabel("Purpose").selectOption("Spent");
    await page.getByLabel("Proceeds (USD)").fill("6000");
    await saveForm(page);

    const tx = await lastTx(page);
    expect(tx).toMatchObject({ type: "Withdrawal", from_account_id: 4, to_account_id: 99, purpose: "Spent" });
    expect(Number(tx.gross_proceeds_usd)).toBe(6000);
    expect(Number(tx.cost_basis_usd)).toBe(2000);
    expect(Number(tx.realized_gain_usd)).toBe(4000);
    expect(tx.holding_period).toBe("LONG");
  });

  test("Spent without proceeds is valued at the day's price", async ({ authedPage: page }) => {
    // Finding F1: the form used to send 0 for a blank, saving $0 proceeds.
    await seedFunds(page.request);
    await openAddForm(page, "Withdrawal");
    await setWhen(page);
    await page.getByLabel("Account").selectOption("Exchange");
    await page.getByLabel("Currency").selectOption("BTC");
    await page.getByLabel("Amount").fill("0.1");
    await page.getByLabel("Purpose").selectOption("Spent");
    await page.getByLabel("Proceeds (USD)").fill("");
    await saveForm(page);
    const tx = await lastTx(page);
    expect(Number(tx.gross_proceeds_usd)).toBe(0.1 * HISTORICAL_PRICE);
  });

  test("Spent proceeds start blank; a typed 0 shows a warning", async ({ authedPage: page }) => {
    await seedFunds(page.request);
    await openAddForm(page, "Withdrawal");
    await page.getByLabel("Account").selectOption("Exchange");
    await page.getByLabel("Currency").selectOption("BTC");
    await page.getByLabel("Purpose").selectOption("Spent");
    await expect(page.getByLabel("Proceeds (USD)")).toHaveValue("");
    await expect(page.getByText("Leave blank to use that day's BTC price as the proceeds.")).toBeVisible();
    await page.getByLabel("Proceeds (USD)").fill("0");
    await expect(page.getByText(/You selected "Spent" but "Proceeds \(USD\)" is 0/)).toBeVisible();
  });

  for (const purpose of ["Gift", "Donation", "Lost"]) {
    test(`${purpose} records FMV and no proceeds`, async ({ authedPage: page }) => {
      await seedFunds(page.request);
      await openAddForm(page, "Withdrawal");
      await setWhen(page);
      await page.getByLabel("Account").selectOption("Exchange");
      await page.getByLabel("Currency").selectOption("BTC");
      await page.getByLabel("Amount").fill("0.1");
      await page.getByLabel("Purpose").selectOption(purpose);
      await expect(page.getByLabel("Proceeds (USD)")).not.toBeEditable();
      await page.getByRole("button", { name: "Refresh" }).click();
      await expect(page.getByLabel("FMV (USD)")).toHaveValue(String(0.1 * HISTORICAL_PRICE));
      await saveForm(page);

      const tx = await lastTx(page);
      expect(tx).toMatchObject({ type: "Withdrawal", purpose });
      expect(Number(tx.fmv_usd)).toBe(0.1 * HISTORICAL_PRICE);
      expect(Number(tx.proceeds_usd ?? 0)).toBe(0);
      // No gain or loss for any of them (Lost too, finding F2).
      expect(Number(tx.realized_gain_usd ?? 0)).toBe(0);
    });
  }

  test("USD withdrawal from the bank", async ({ authedPage: page }) => {
    await seedFunds(page.request);
    await openAddForm(page, "Withdrawal");
    await setWhen(page);
    await page.getByLabel("Account").selectOption("Bank");
    await expect(page.getByLabel("Purpose")).toHaveCount(0);
    await page.getByLabel("Amount").fill("500");
    await saveForm(page);
    const tx = await lastTx(page);
    expect(tx).toMatchObject({ type: "Withdrawal", from_account_id: 1, to_account_id: 99 });
    expect(Number(tx.amount)).toBe(500);
  });
});

test("transfer Exchange → Wallet with a BTC network fee", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Transfer");
  await setWhen(page);
  await page.getByLabel("From Account").selectOption("Exchange");
  await page.getByLabel("From Currency").selectOption("BTC");
  await expect(page.getByLabel("To Account")).toHaveValue("Wallet");
  await page.getByLabel("Amount (From)").fill("0.5");
  await page.getByLabel("Amount (To)").fill("0.4999");
  await expect(page.getByLabel("Fee (BTC)")).toHaveValue("0.0001");
  // No made-up USD estimate next to the fee (it used a fixed $30,000: F4).
  await expect(page.getByText(/~ \$/)).toHaveCount(0);
  await saveForm(page);

  const tx = await lastTx(page);
  expect(tx).toMatchObject({ type: "Transfer", from_account_id: 4, to_account_id: 2, fee_currency: "BTC" });
  expect(Number(tx.amount)).toBe(0.5);
  expect(Number(tx.fee_amount)).toBe(0.0001);

  const balances = await (await page.request.get("/api/calculations/accounts/balances")).json();
  const by = Object.fromEntries(balances.map((b: { name: string; balance: string }) => [b.name, Number(b.balance)]));
  expect(by["Wallet"]).toBe(0.4999);
  expect(by["Exchange BTC"]).toBe(0.5);
});

test("transfer Bank → Exchange USD", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Transfer");
  await setWhen(page);
  await page.getByLabel("From Account").selectOption("Bank");
  await expect(page.getByLabel("To Account")).toHaveValue("Exchange");
  await expect(page.getByLabel("To Currency")).toHaveValue("USD");
  await page.getByLabel("Amount (From)").fill("2500");
  await page.getByLabel("Amount (To)").fill("2500");
  await saveForm(page);
  const tx = await lastTx(page);
  expect(tx).toMatchObject({ type: "Transfer", from_account_id: 1, to_account_id: 3 });
  expect(Number(tx.amount)).toBe(2500);
});

for (const [from, id] of [["Exchange", 3], ["Bank", 1]] as const) {
  test(`buy from ${from} with a USD fee`, async ({ authedPage: page }) => {
    await createTx(page.request, {
      type: "Deposit", timestamp: "2023-01-02T18:00:00Z", from_account_id: 99, to_account_id: id,
      amount: "50000", fee_amount: "0", fee_currency: "USD", source: "N/A",
    });
    await openAddForm(page, "Buy");
    await setWhen(page);
    await page.getByLabel("From Account").selectOption(from);
    await page.getByLabel("Amount USD").fill("10000");
    await page.getByLabel("Amount BTC").fill("0.2");
    await page.getByLabel("Fee (USD)").fill("25");
    await saveForm(page);

    const tx = await lastTx(page);
    expect(tx).toMatchObject({ type: "Buy", from_account_id: id, to_account_id: 4, fee_currency: "USD" });
    expect(Number(tx.amount)).toBe(0.2);
    expect(Number(tx.fee_amount)).toBe(25);
    expect(Number(tx.cost_basis_usd)).toBe(10000);
  });
}

test("sell with a USD fee: proceeds net of the fee, short-term gain", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Sell");
  await page.getByLabel("Date & Time").fill("2023-06-01T09:00:05");
  await expect(page.getByLabel("Account")).toHaveValue("Exchange");
  await page.getByLabel("Amount BTC").fill("0.25");
  await page.getByLabel("Gross Proceeds (USD)").fill("7000");
  await page.getByLabel("Fee (USD)").fill("20");
  await saveForm(page);

  const tx = await lastTx(page);
  expect(tx).toMatchObject({ type: "Sell", from_account_id: 4, to_account_id: 3, holding_period: "SHORT" });
  expect(Number(tx.gross_proceeds_usd)).toBe(7000);
  expect(Number(tx.proceeds_usd)).toBe(6980);
  expect(Number(tx.cost_basis_usd)).toBe(5000);
  expect(Number(tx.realized_gain_usd)).toBe(1980);
  await expect(page.getByRole("listitem").filter({ hasText: "Sell" })).toContainText("Gain: +$1980.00");
});

test("sell with the 1099-DA override", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Sell");
  await setWhen(page, "2025-03-01T09:00:05");
  await page.getByLabel("Amount BTC").fill("0.1");
  await page.getByLabel("Gross Proceeds (USD)").fill("9000");
  await page.getByLabel("Broker form (1099-DA / 1099-B)").selectOption("basis");
  await saveForm(page);
  const tx = await lastTx(page);
  expect(tx.broker_reporting).toBe("basis");
});

test("a sell larger than the balance is refused with a message", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openAddForm(page, "Sell");
  await setWhen(page);
  await page.getByLabel("Amount BTC").fill("5");
  await page.getByLabel("Gross Proceeds (USD)").fill("1000");
  await page.getByRole("button", { name: "Save Transaction" }).click();
  await expect(page.getByText(/Failed to create transaction/)).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(2);
});
