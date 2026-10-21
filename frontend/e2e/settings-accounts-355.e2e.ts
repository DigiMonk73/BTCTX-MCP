// Settings' "Wallets, exchanges and banks" (#355, spec 5.9): a wallet and an
// exchange added there, hidden and shown; a Buy and a Sell on the second
// exchange, edited and saved unchanged, keep its accounts; and its 1099-DA
// switch asks first on a ledger with an earlier year (5.8, B6c's stub). Only
// that accounts are kept, never figures: an added account's figures wait for
// B3 on this branch.
import { test, expect, createTx, listTx, saveForm, seedFunds } from "./fixtures";
import type { APIRequestContext, Page } from "@playwright/test";

async function openSection(page: Page) {
  await page.getByRole("link", { name: "Settings" }).click();
  const section = page.getByRole("region", { name: "Wallets, exchanges and banks" });
  await expect(section.getByRole("list", { name: "Your accounts" })).toBeVisible();
  return section;
}

async function add(page: Page, label: string, name: string) {
  const section = page.getByRole("region", { name: "Wallets, exchanges and banks" });
  await section.getByRole("button", { name: label }).click();
  const form = section.getByRole("form", { name: label });
  await form.getByLabel("Nickname").fill(name);
  await form.getByRole("button", { name: "Add", exact: true }).click();
  await expect(page.getByText("Added.")).toBeVisible();
  await expect(form).toHaveCount(0);
}

async function accountIds(request: APIRequestContext): Promise<Record<string, number>> {
  const r = await request.get("/api/accounts/");
  expect(r.ok()).toBeTruthy();
  const rows = (await r.json()) as Array<{ id: number; name: string }>;
  return Object.fromEntries(rows.map((a) => [a.name, a.id]));
}

async function editUnchanged(page: Page, type: string) {
  await page.goto("/transactions"); // a fresh list: the row was saved over the API
  await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
  const row = page.getByRole("listitem").filter({ hasText: type }).first();
  await row.getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await saveForm(page, "Update Transaction");
}

test("a wallet and an exchange added in Settings, hidden and shown", async ({ authedPage: page }) => {
  const section = await openSection(page);
  await add(page, "Add a wallet", "Cold Storage");
  await add(page, "Add an exchange", "Kraken");
  for (const name of ["Cold Storage", "Kraken USD", "Kraken BTC"]) {
    await expect(section.getByRole("listitem", { name })).toBeVisible();
  }

  const wallet = section.getByRole("listitem", { name: "Cold Storage" });
  await wallet.getByRole("button", { name: "Hide" }).click();
  await expect(wallet.getByText("Hidden", { exact: true })).toBeVisible();
  await wallet.getByRole("button", { name: "Show" }).click();
  await expect(wallet.getByText("Hidden", { exact: true })).toHaveCount(0);

  // Kept after a reload: the server has them
  await page.reload();
  await expect(section.getByRole("listitem", { name: "Kraken BTC" })).toBeVisible();
  const ids = await accountIds(page.request);
  expect(ids["Cold Storage"]).toBeGreaterThanOrEqual(100);
});

test("a Buy and a Sell on the second exchange keep its accounts", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await openSection(page);
  await add(page, "Add an exchange", "Kraken");
  const ids = await accountIds(page.request);
  const usd = ids["Kraken USD"];
  const btc = ids["Kraken BTC"];

  await createTx(page.request, {
    type: "Transfer", timestamp: "2024-01-01T12:00:00Z", from_account_id: 1, to_account_id: usd,
    amount: "20000", fee_amount: "0", fee_currency: "USD",
  });
  const buy = await createTx(page.request, {
    type: "Buy", timestamp: "2024-06-15T15:00:00Z", from_account_id: usd, to_account_id: btc,
    amount: "0.1", cost_basis_usd: "6000.00", fee_amount: "5", fee_currency: "USD",
  });
  await editUnchanged(page, "Buy");
  const sell = await createTx(page.request, {
    type: "Sell", timestamp: "2024-07-15T15:00:00Z", from_account_id: btc, to_account_id: usd,
    amount: "0.05", gross_proceeds_usd: "3200", fee_amount: "3", fee_currency: "USD",
  });
  await editUnchanged(page, "Sell");

  const after = await listTx(page.request);
  const kept = (id: unknown) => {
    const t = after.find((x) => x.id === id)!;
    return [t.from_account_id, t.to_account_id];
  };
  expect(kept(buy.id)).toEqual([usd, btc]);
  expect(kept(sell.id)).toEqual([btc, usd]);
});

test("the 1099-DA switch asks first when an earlier year has the exchange's transactions", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  const section = await openSection(page);
  await add(page, "Add an exchange", "Kraken");
  const ids = await accountIds(page.request);
  await createTx(page.request, {
    type: "Transfer", timestamp: "2024-01-01T12:00:00Z", from_account_id: 1, to_account_id: ids["Kraken USD"],
    amount: "500", fee_amount: "0", fee_currency: "USD",
  });
  await page.reload();
  const row = section.getByRole("listitem", { name: "Kraken BTC" });
  const sendsForm = row.getByRole("checkbox", { name: "This exchange sends me a Form 1099-DA" });
  await expect(sendsForm).toBeChecked();

  const asked: string[] = [];
  let answer = false;
  page.on("dialog", async (d) => {
    asked.push(d.message());
    await (answer ? d.accept() : d.dismiss());
  });

  await sendsForm.click();
  await expect(page.getByText("Not changed.")).toBeVisible();
  await expect(sendsForm).toBeChecked();
  expect(asked[0]).toContain("This changes the figures of tax year 2024");

  answer = true;
  await sendsForm.click();
  await expect(page.getByText("Saved.")).toBeVisible();
  await expect(sendsForm).not.toBeChecked();
  const r = await page.request.get("/api/accounts/");
  const listed = (await r.json()) as Array<{ id: number; sends_1099da: boolean | null }>;
  expect(listed.find((a) => a.id === ids["Kraken BTC"])?.sends_1099da).toBe(false);
});
