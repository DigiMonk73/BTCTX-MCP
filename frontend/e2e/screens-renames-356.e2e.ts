// B8's screens (#356; 2.0 spec 5.13, P7's mockups on #572): the dashboard's
// cards and their "Show accounts (n)", a renamed Wallet on its card and in
// the list, and the Transactions page's account filter. Elements by role and
// name, as the mockups name them.
import { test, expect, parseFigure, seedKnownLedger } from "./fixtures";
import type { APIRequestContext, Page } from "@playwright/test";

async function addAccount(request: APIRequestContext, kind: string, name: string) {
  const r = await request.post("/api/accounts/", { data: { kind, name } });
  expect(r.status(), await r.text()).toBe(201);
}

async function rename(request: APIRequestContext, id: number, name: string) {
  const r = await request.put(`/api/accounts/${id}`, { data: { name } });
  expect(r.ok(), await r.text()).toBeTruthy();
}

const card = (page: Page, kind: string) => page.getByRole("region", { name: kind, exact: true });

test("a card with more than one account opens to list them, and stays open", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await addAccount(page.request, "wallet", "Coldcard");
  await page.reload();

  const wallet = card(page, "Wallet");
  const toggle = wallet.getByRole("button", { name: "Show accounts (2)" });
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await expect(wallet.getByRole("list", { name: "Wallet accounts" })).toBeHidden();
  // The other kinds have one account each: no toggle
  await expect(card(page, "Bank").getByRole("button")).toHaveCount(0);

  await toggle.click();
  const list = wallet.getByRole("list", { name: "Wallet accounts" });
  await expect(list).toBeVisible();
  await expect(list.getByRole("listitem")).toHaveText([/^Wallet\s*0\.50990000 BTC$/, /^Coldcard\s*0\.00000000 BTC$/]);
  await expect(wallet.getByRole("button", { name: "Hide accounts" })).toHaveAttribute("aria-expanded", "true");

  await page.reload(); // remembered in this browser
  await expect(card(page, "Wallet").getByRole("list", { name: "Wallet accounts" })).toBeVisible();
});

test("each exchange is one row, its dollars and bitcoin side by side", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await addAccount(page.request, "exchange", "Kraken");
  await page.reload();
  const exchange = card(page, "Exchange");
  await exchange.getByRole("button", { name: "Show accounts (2)" }).click();
  await expect(exchange.getByRole("list", { name: "Exchange accounts" }).getByRole("listitem")).toHaveText([
    /^Exchange\s*\$15,980\.00\s*0\.15000000 BTC$/, /^Kraken\s*\$0\.00\s*0\.00000000 BTC$/]);
});

test("a renamed Wallet stays on the Wallet card and is named by its new name", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await rename(page.request, 2, "Phone Wallet");
  await page.reload();
  const total = card(page, "Wallet").locator(".account-card-total");
  expect(parseFigure(await total.innerText())).toBe(0.5099);

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

test("on a phone the cards stack and the toggle is a 44 px target", async ({ authedPage: page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await addAccount(page.request, "bank", "Credit Union");
  await page.reload();
  const toggle = card(page, "Bank").getByRole("button", { name: "Show accounts (2)" });
  expect((await toggle.boundingBox())?.height).toBeGreaterThanOrEqual(44);
  const [bank, exchange] = [await card(page, "Bank").boundingBox(), await card(page, "Exchange").boundingBox()];
  expect(exchange!.y).toBeGreaterThan(bank!.y + bank!.height - 1);
});
