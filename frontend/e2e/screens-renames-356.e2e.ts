// B8 (#356, spec 5.13 and 5.9's Rename): the dashboard's rows by kind, a
// renamed Wallet that stays on the dashboard, Transactions' names from the
// book with its account filter, Ledger Review's items naming their accounts,
// and Settings' Rename. Only names and balances, never figures that need B3:
// an added account's lots and gains wait for B3 on this draft branch.
import { test, expect, createTx, seedFunds } from "./fixtures";
import type { APIRequestContext, Page } from "@playwright/test";

async function addAccount(request: APIRequestContext, kind: string, name: string): Promise<Record<string, number>> {
  const r = await request.post("/api/accounts/", { data: { kind, name } });
  expect(r.status()).toBe(201);
  const rows = (await r.json()) as Array<{ id: number; currency: string }>;
  return Object.fromEntries(rows.map((a) => [a.currency, a.id]));
}

/** The Portfolio Overview's rows, label and figures, in order, down to Total BTC. */
async function overviewRows(page: Page): Promise<string[]> {
  const card = page.locator(".portfolio-overview");
  await expect(card.getByText("Total BTC")).toBeVisible();
  const lines = await card.getByRole("paragraph").evaluateAll((ps) =>
    ps.map((p) => `${p.querySelector("strong")?.textContent}: ${p.querySelector("span")?.textContent}`));
  return lines.slice(0, lines.findIndex((line) => line.startsWith("Total BTC")));
}

/** Rename `from` in Settings to `to`; `listed` is the row it then has (an exchange's: "<to> BTC"). */
async function renameInSettings(page: Page, from: string, to: string, listed = to) {
  await page.getByRole("link", { name: "Settings" }).click();
  const section = page.getByRole("region", { name: "Wallets, exchanges and banks" });
  await section.getByRole("listitem", { name: from, exact: true }).getByRole("button", { name: "Rename" }).click();
  const form = section.getByRole("form", { name: `Rename ${from}` });
  await form.getByLabel("Nickname").fill(to);
  await form.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Renamed.")).toBeVisible();
  await expect(section.getByRole("listitem", { name: listed, exact: true })).toBeVisible();
}

test("the dashboard's rows by kind, and a renamed Wallet stays on it", async ({ authedPage: page }) => {
  await seedFunds(page.request); // Bank $100,000 in, 1 BTC bought on Exchange for $20,000
  const cold = (await addAccount(page.request, "wallet", "Cold Storage")).BTC;
  await addAccount(page.request, "exchange", "Kraken");
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-03-01T12:00:00Z", from_account_id: 99, to_account_id: cold,
    amount: "0.5", source: "MyBTC", cost_basis_usd: "10000", fee_amount: "0", fee_currency: "BTC",
  });
  await page.reload();
  expect(await overviewRows(page)).toEqual([
    "Bank: $80,000.00",
    "Wallet: 0.00000000 BTC",
    "Cold Storage: 0.50000000 BTC",
    "Exchange: $0.00 · 1.00000000 BTC",
    "Kraken: $0.00 · 0.00000000 BTC",
  ]);

  await renameInSettings(page, "Wallet", "Phone Wallet");
  await page.getByRole("link", { name: "Dashboard" }).click();
  expect(await overviewRows(page)).toContain("Phone Wallet: 0.00000000 BTC");
  expect((await overviewRows(page)).some((line) => line.startsWith("Wallet:"))).toBe(false);
});

test("Transactions: an exchange's name, Consolidation, and the account filter", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  const kraken = await addAccount(page.request, "exchange", "Kraken");
  await createTx(page.request, {
    type: "Transfer", timestamp: "2024-01-01T12:00:00Z", from_account_id: 1, to_account_id: kraken.USD,
    amount: "20000", fee_amount: "0", fee_currency: "USD",
  });
  await createTx(page.request, {
    type: "Buy", timestamp: "2024-02-01T12:00:00Z", from_account_id: kraken.USD, to_account_id: kraken.BTC,
    amount: "0.1", cost_basis_usd: "6000.00", fee_amount: "0", fee_currency: "USD",
  });
  await createTx(page.request, {
    type: "Transfer", timestamp: "2024-03-01T12:00:00Z", from_account_id: 4, to_account_id: 4,
    amount: "0.5", fee_amount: "0.0001", fee_currency: "BTC", fee_usd: "5.00",
  });

  await page.getByRole("link", { name: "Transactions" }).click();
  const rows = page.getByRole("listitem");
  await expect(rows).toHaveCount(5);
  await expect(rows.filter({ hasText: "Buy · Kraken" })).toHaveCount(1);
  await expect(rows.filter({ hasText: "Exchange BTC → Exchange BTC" })).toContainText("Consolidation");
  await expect(page.getByText("Between exchanges")).toHaveCount(0);

  const filter = page.getByLabel("Filter by wallet, exchange or bank");
  await filter.selectOption({ label: "Kraken USD" });
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: "Bank → Kraken USD" })).toHaveCount(1);
  await filter.selectOption({ label: "Kraken BTC" });
  await expect(rows).toHaveCount(1);
  await expect(rows.first()).toContainText("Buy · Kraken");
  await filter.selectOption({ label: "All accounts" });
  await expect(rows).toHaveCount(5);
});

test("Ledger Review's items name their account by its nickname", async ({ authedPage: page }) => {
  // A My BTC deposit with no date originally acquired is a reminder (into 2: the checks
  // read 1.x's accounts until B3)
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-03-01T12:00:00Z", from_account_id: 99, to_account_id: 2,
    amount: "0.25", source: "MyBTC", cost_basis_usd: "10000", fee_amount: "0", fee_currency: "BTC",
  });
  await renameInSettings(page, "Wallet", "Phone Wallet");
  await page.getByRole("button", { name: "Check again" }).click();
  await page.getByRole("button", { name: /^Show the 1 deposit/ }).click();
  await expect(page.getByText(/0\.25000000 BTC · Phone Wallet —/)).toBeVisible();
});

test("an exchange renamed in Settings renames both its accounts, and back", async ({ authedPage: page }) => {
  await renameInSettings(page, "Exchange BTC", "Coinbase", "Coinbase BTC");
  const section = page.getByRole("region", { name: "Wallets, exchanges and banks" });
  await expect(section.getByRole("listitem", { name: "Coinbase USD", exact: true })).toBeVisible();
  await renameInSettings(page, "Coinbase USD", "Exchange", "Exchange USD");
  await expect(section.getByRole("listitem", { name: "Exchange BTC", exact: true })).toBeVisible();
});
