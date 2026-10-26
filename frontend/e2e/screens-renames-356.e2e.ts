// B8's screens (#356; 2.0 spec 5.9, 5.13): Portfolio Overview's caret on a
// kind with more than one account (#674, in place of P7's cards), a renamed
// Wallet on its line and in the list, the Transactions page's account
// filter, and Settings' Rename. Elements by role and name.
import { test, expect, createTx, figure, openSection, parseFigure, seedKnownLedger } from "./fixtures";
import type { APIRequestContext, Locator, Page } from "@playwright/test";

async function addAccount(request: APIRequestContext, kind: string, name: string) {
  const r = await request.post("/api/accounts/", { data: { kind, name } });
  expect(r.status(), await r.text()).toBe(201);
}

async function rename(request: APIRequestContext, id: number, name: string) {
  const r = await request.put(`/api/accounts/${id}`, { data: { name } });
  expect(r.ok(), await r.text()).toBeTruthy();
}

const overview = (page: Page) => page.locator(".portfolio-overview");
/** A kind's line as a button, named by its label and its total. */
const caret = (page: Page, label: string) =>
  overview(page).getByRole("button", { name: new RegExp(`^${label.replace(/[()]/g, "\\$&")}`) });
const accounts = (page: Page, label: string) => overview(page).getByRole("list", { name: `${label} accounts` });

async function listed(list: Locator): Promise<number[]> {
  return (await list.locator(".balance-line-amount").allInnerTexts()).map(parseFigure);
}

test("a kind with more than one account has a caret that lists them, and stays open", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await addAccount(page.request, "wallet", "Coldcard");
  await page.reload();

  const toggle = caret(page, "Wallet (BTC)");
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(accounts(page, "Wallet (BTC)")).toBeHidden();
  // The other kinds have one account each: no caret, 1.x's lines
  await expect(overview(page).getByRole("button")).toHaveCount(1);
  expect(await figure(page, "Wallet (BTC)")).toBe(0.5099);

  await toggle.click();
  const list = accounts(page, "Wallet (BTC)");
  await expect(list).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-controls", (await list.getAttribute("id"))!);
  // Each with what its BTC cost (#709): the empty Coldcard's nothing
  await expect(list.getByRole("listitem")).toHaveText([/^Wallet\s*0\.50990000 BTC\s*Cost basis \$[\d,]+\.\d\d/,
    /^Coldcard\s*0\.00000000 BTC\s*Cost basis \$0\.00/]);
  await expect(toggle).toHaveAttribute("aria-expanded", "true");

  await page.reload(); // remembered in this browser
  await expect(accounts(page, "Wallet (BTC)")).toBeVisible();
  await caret(page, "Wallet (BTC)").press("Enter"); // and closed from the keyboard
  await expect(accounts(page, "Wallet (BTC)")).toBeHidden();
});

test("each exchange's dollars under Exchange (USD), its bitcoin under Exchange (BTC), adding up to the line", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await addAccount(page.request, "exchange", "Kraken");
  // Dollars into Kraken USD (id 100: the first account added), so each exchange line lists two figures above zero
  await createTx(page.request, { type: "Transfer", timestamp: "2024-04-01T15:00:00Z", from_account_id: 1,
    to_account_id: 100, amount: "250.50", fee_amount: "0", fee_currency: "USD" });
  await page.reload();

  await caret(page, "Exchange (USD)").click();
  await caret(page, "Exchange (BTC)").click();
  await expect(accounts(page, "Exchange (USD)").getByRole("listitem")).toHaveText([
    /^Exchange\s*\$15,980\.00$/, /^Kraken\s*\$250\.50$/]);
  await expect(accounts(page, "Exchange (BTC)").getByRole("listitem")).toHaveText([
    /^Exchange\s*0\.15000000 BTC\s*Cost basis \$[\d,]+\.\d\d/, /^Kraken\s*0\.00000000 BTC\s*Cost basis \$0\.00/]);
  const sum = (figures: number[], unit: number) => figures.reduce((total, f) => total + Math.round(f * unit), 0);
  expect(sum(await listed(accounts(page, "Exchange (USD)")), 100)).toBe(Math.round((await figure(page, "Exchange (USD)")) * 100));
  expect(sum(await listed(accounts(page, "Exchange (BTC)")), 1e8)).toBe(Math.round((await figure(page, "Exchange (BTC)")) * 1e8));
  expect(await figure(page, "Bank (USD)")).toBe(80000 - 250.5);
});

test("a renamed Wallet stays on Wallet (BTC) and is named by its new name", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await rename(page.request, 2, "Phone Wallet");
  await page.reload();
  expect(await figure(page, "Wallet (BTC)")).toBe(0.5099);

  await page.getByRole("link", { name: "Transactions" }).click();
  const transfer = page.getByRole("listitem").filter({ hasText: "Transfer" });
  await expect(transfer).toContainText("Exchange BTC → Phone Wallet");
});

test("the account filter keeps one account's rows, or a kind's", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await rename(page.request, 2, "Phone Wallet");
  await page.getByRole("link", { name: "Transactions" }).click();
  await expect(page.getByRole("listitem")).toHaveCount(6);

  const filter = page.getByLabel("Filter transactions");
  await filter.selectOption({ label: "Phone Wallet" });
  // The transfer into it and the income it received
  await expect(page.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByText("2 of 6 transactions", { exact: true })).toBeVisible();

  await filter.selectOption({ label: "Bank" });
  await expect(page.getByRole("listitem")).toHaveCount(2); // the deposit and the Buy it paid for

  await filter.selectOption({ label: "All accounts" });
  await expect(page.getByRole("listitem")).toHaveCount(6);
  await expect(page.getByText(/ of 6 transactions$/)).toHaveCount(0);
});

test("on a phone the card keeps its lines' spacing and the whole line is the caret's target", async ({ authedPage: page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await addAccount(page.request, "bank", "Credit Union");
  await page.reload();
  const toggle = caret(page, "Bank (USD)");
  const [box, line] = [await toggle.boundingBox(), await toggle.locator("xpath=..").boundingBox()];
  expect(box!.height).toBeGreaterThanOrEqual(24); // WCAG 2.5.8
  expect(box!.width).toBeCloseTo(line!.width, 0);
  // The lines as far apart as with no caret: Bank to Exchange (USD) as Exchange (USD) to Exchange (BTC)
  const tops = await overview(page).locator("p").evaluateAll((ps) => ps.slice(0, 3).map((p) => p.getBoundingClientRect().top));
  expect(tops[1] - tops[0]).toBeCloseTo(tops[2] - tops[1], 0);
  const [card, price] = [await overview(page).boundingBox(), await page.getByRole("heading", { name: "Current Bitcoin Price" }).boundingBox()];
  expect(price!.y).toBeGreaterThan(card!.y + card!.height - 1);
});

async function accountsSection(page: Page) {
  await page.getByRole("link", { name: "Settings" }).click();
  return openSection(page, "Wallets, exchanges and banks");
}

test("Settings' Rename renames a wallet and an exchange, and the list names them so", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  const section = await accountsSection(page);

  await section.getByRole("button", { name: /^Wallet\b/ }).click();
  const wallet = section.getByRole("region", { name: "Wallet" });
  await expect(wallet.getByRole("button", { name: "Rename" })).toBeDisabled(); // its own name: nothing to send
  await wallet.getByLabel("Name").fill("Phone Wallet");
  await wallet.getByRole("button", { name: "Rename" }).click();
  await expect(section.getByRole("button", { name: /^Phone Wallet\b/ })).toBeVisible();

  await section.getByRole("button", { name: /^Exchange\b/ }).click();
  const exchange = section.getByRole("region", { name: "Exchange" });
  await exchange.getByLabel("Name").fill("Coinbase");
  await expect(exchange.getByText(
    "BitcoinTX keeps an exchange's dollars and bitcoin as two accounts, 'Coinbase USD' and 'Coinbase BTC'.",
  )).toBeVisible();
  await exchange.getByRole("button", { name: "Rename" }).click();
  await expect(section.getByRole("button", { name: /^Coinbase\b/ })).toBeVisible();

  await page.getByRole("link", { name: "Transactions" }).click();
  await expect(page.getByRole("listitem").filter({ hasText: "Transfer" })).toContainText("Coinbase BTC \u2192 Phone Wallet");
  await expect(page.getByRole("listitem").filter({ hasText: "Buy" })).toContainText("Coinbase");
});

test("Settings' Rename says what the server refuses, in its words", async ({ authedPage: page }) => {
  const section = await accountsSection(page);
  await section.getByRole("button", { name: /^Bank\b/ }).click();
  const bank = section.getByRole("region", { name: "Bank" });
  await bank.getByLabel("Name").fill("Wallet");
  await bank.getByRole("button", { name: "Rename" }).click();
  await expect(section.getByRole("alert")).toHaveText(
    "'Wallet' always means your first wallet in files (CSV, River, BitcoinTX 1.x): choose another name.");
  await expect(section.getByRole("button", { name: /^Bank\b/ })).toBeVisible();
});

