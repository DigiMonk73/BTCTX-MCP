// The UI as it renders, recorded for a before/after comparison when the
// frontend is reorganised without meaning to change it: every page, and the
// transaction form for each type and its variants, as the accessibility tree
// (labels, roles, text: what these specs find elements by) and as HTML.
// Skipped unless UI_SNAPSHOT_DIR is set:
//   UI_SNAPSHOT_DIR=/tmp/ui-before npx playwright test ui-snapshot --project=chicago
//   (change the code, rebuild, run again into /tmp/ui-after)
//   diff -r /tmp/ui-before /tmp/ui-after
import { test, expect, openAddForm, seedKnownLedger } from "./fixtures";
import type { Page } from "@playwright/test";
import { mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const OUT = process.env.UI_SNAPSHOT_DIR ?? "";
test.skip(!OUT, "set UI_SNAPSHOT_DIR to record the UI");

const RIVER_CSV = [
  "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag",
  "2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy",
  "2026-02-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell",
  "2026-02-01 09:00:00,,,0.00002000,BTC,,,Interest",
  "2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,",
  "2026-03-01 10:00:00,,,0.00060000,BTC,,,",
  "not-a-date,1,USD,1,BTC,,,Buy",
].join("\n") + "\n";

const CSV = [
  "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes",
  "2024-01-01T10:00:00Z,Deposit,20000,External,Bank,,,,,,,",
  "2024-01-02T10:00:00Z,Buy,0.1,Bank,Exchange BTC,4000,,10,USD,,,",
  "2024-01-03T10:00:00Z,Sell,5,Exchange BTC,Exchange USD,,100,,,,,",
].join("\n") + "\n";

/** Today's date as the add form fills it (local time, YYYY-MM-DD). */
function today(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** Without what changes on its own: the time the add form's date starts
 * at, and the test server's port in the AI setup text. */
function stable(text: string): string {
  return text
    .replace(new RegExp(`${today()}T\\d{2}:\\d{2}(:\\d{2})?`, "g"), "<now>")
    .replace(/127\.0\.0\.1:\d+/g, "127.0.0.1:<port>");
}

async function record(page: Page, name: string) {
  mkdirSync(OUT, { recursive: true });
  await page.waitForLoadState("networkidle");
  const body = page.locator("body");
  writeFileSync(path.join(OUT, `${name}.aria.txt`), stable(await body.ariaSnapshot()) + "\n");
  writeFileSync(path.join(OUT, `${name}.html`), stable(await body.innerHTML()) + "\n");
}

async function select(page: Page, label: string, value: string) {
  await page.getByLabel(label, { exact: true }).selectOption(value);
}

test("pages", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await page.goto("/dashboard");
  await expect(page.getByText("Loading")).toHaveCount(0);
  await record(page, "dashboard");
  await page.getByRole("link", { name: "Transactions" }).click();
  await expect(page.getByRole("listitem").first()).toBeVisible();
  await record(page, "transactions");
  await page.getByRole("link", { name: "Reports" }).click();
  await record(page, "reports");
  await page.getByRole("link", { name: "Settings" }).click();
  await record(page, "settings");
});

test("login and register", async ({ page }) => {
  await page.goto("/login");
  await record(page, "login");
  await page.goto("/register");
  await record(page, "register");
});

const FORM_VARIANTS: Array<[string, string, Array<[string, string]>]> = [
  ["deposit-empty", "Deposit", []],
  ["deposit-bank", "Deposit", [["Account", "Bank"]]],
  ["deposit-wallet", "Deposit", [["Account", "Wallet"]]],
  ["deposit-wallet-income", "Deposit", [["Account", "Wallet"], ["Source", "Income"]]],
  ["deposit-exchange-usd", "Deposit", [["Account", "Exchange"], ["Currency", "USD"]]],
  ["deposit-exchange-btc", "Deposit", [["Account", "Exchange"], ["Currency", "BTC"], ["Source", "Gift"]]],
  ["withdrawal-bank", "Withdrawal", [["Account", "Bank"]]],
  ["withdrawal-wallet-spent", "Withdrawal", [["Account", "Wallet"], ["Purpose (BTC only)", "Spent"]]],
  ["withdrawal-wallet-gift", "Withdrawal", [["Account", "Wallet"], ["Purpose (BTC only)", "Gift"]]],
  ["withdrawal-exchange-btc-lost", "Withdrawal",
    [["Account", "Exchange"], ["Currency", "BTC"], ["Purpose (BTC only)", "Lost"]]],
  ["transfer-bank", "Transfer", [["From Account", "Bank"]]],
  ["transfer-wallet", "Transfer", [["From Account", "Wallet"]]],
  ["transfer-exchange-usd", "Transfer", [["From Account", "Exchange"], ["From Currency", "USD"]]],
  ["transfer-exchange-btc", "Transfer", [["From Account", "Exchange"], ["From Currency", "BTC"]]],
  ["buy", "Buy", []],
  ["buy-bank", "Buy", [["From Account", "Bank"]]],
  ["sell", "Sell", []],
];

for (const [name, type, choices] of FORM_VARIANTS) {
  test(`add form: ${name}`, async ({ authedPage: page }) => {
    await openAddForm(page, type);
    for (const [label, value] of choices) await select(page, label, value);
    await record(page, `form-${name}`);
  });
}

test("add form: a Spent withdrawal with a fee and $0 proceeds", async ({ authedPage: page }) => {
  await openAddForm(page, "Withdrawal");
  await select(page, "Account", "Wallet");
  await select(page, "Purpose (BTC only)", "Spent");
  await page.getByLabel("Amount", { exact: true }).fill("0.1");
  await page.getByLabel("Fee (BTC)").fill("0.0001");
  await page.getByLabel("Proceeds (USD)").fill("0");
  await record(page, "form-withdrawal-spent-zero-proceeds");
});

test("add form: a BTC transfer's fee from its amounts", async ({ authedPage: page }) => {
  await openAddForm(page, "Transfer");
  await select(page, "From Account", "Wallet");
  await page.getByLabel("Amount (From)").fill("0.5");
  await page.getByLabel("Amount (To)").fill("0.4999");
  await record(page, "form-transfer-btc-fee");
});

test("add form: errors on an empty save", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await select(page, "Account", "Wallet");
  await page.getByRole("button", { name: "Save Transaction" }).click();
  await record(page, "form-deposit-errors");
});

test("edit forms", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await page.getByRole("link", { name: "Transactions" }).click();
  const count = await page.getByRole("listitem").count();
  for (let i = 0; i < count; i++) {
    await page.goto("/transactions");
    await page.getByRole("listitem").nth(i).getByRole("button", { name: "Edit" }).click();
    await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
    await record(page, `edit-${i}`);
  }
});

test("imports", async ({ authedPage: page }) => {
  await page.getByRole("link", { name: "Settings" }).click();
  const river = page.getByRole("region", { name: "Import from River" });
  await river.getByLabel("River CSV file").setInputFiles({
    name: "river.csv", mimeType: "text/csv", buffer: Buffer.from(RIVER_CSV),
  });
  await river.getByRole("button", { name: "Preview" }).click();
  await expect(river.getByText(/rows in file/)).toBeVisible();
  await record(page, "river-preview");

  const data = page.getByRole("region", { name: "Data Management" });
  await data.locator("#csv-file-input").setInputFiles({
    name: "import.csv", mimeType: "text/csv", buffer: Buffer.from(CSV),
  });
  await data.getByRole("button", { name: /Preview/ }).click();
  await expect(data.getByText(/row/).first()).toBeVisible();
  await record(page, "csv-preview");
});
