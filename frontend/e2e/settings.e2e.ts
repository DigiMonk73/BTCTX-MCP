// Settings: timezone, recalculation, credentials, delete, backup and
// restore, CSV export, and the Connect an AI Assistant prompt.
import {
  test, expect, seedKnownLedger, createTx, listTx, loginViaUi, acceptDialogs, USER, PASSWORD,
} from "./fixtures";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";

async function openSettings(page: Page) {
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByText("Recalculate Ledger")).toBeVisible();
}

async function historyCsv(page: Page, year: number) {
  const r = await page.request.get(`/api/reports/simple_transaction_history?year=${year}&format=csv`);
  expect(r.ok()).toBeTruthy();
  return r.text();
}

test("changing the tax timezone moves a sale across the year boundary", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  // 20:00 UTC on Dec 31: still 2024 in Chicago, already 2025 in Tokyo.
  await createTx(page.request, {
    type: "Sell", timestamp: "2024-12-31T20:00:00Z", from_account_id: 4, to_account_id: 3,
    amount: "0.01", gross_proceeds_usd: "900", fee_amount: "0", fee_currency: "USD",
  });
  await openSettings(page);
  const select = page.getByLabel("Tax timezone");
  await expect(select).toHaveValue("America/Chicago");
  await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  expect((await historyCsv(page, 2024)).match(/Sell/g)).toHaveLength(2);

  await select.selectOption("Asia/Tokyo");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("Tax timezone set to Asia/Tokyo. Gains were recalculated.")).toBeVisible();
  expect((await historyCsv(page, 2024)).match(/Sell/g)).toHaveLength(1);
  expect((await historyCsv(page, 2025)).match(/Sell/g)).toHaveLength(1);
});

test("recalculate ledger leaves the figures unchanged", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  const before = await listTx(page.request);
  await openSettings(page);
  await page.getByRole("button", { name: "Recalculate" }).click();
  await expect(page.getByText("Recalculated 6 transaction(s).")).toBeVisible();
  const after = await listTx(page.request);
  const strip = (t: Record<string, unknown>[]) =>
    t.map((x) => Object.fromEntries(Object.entries(x).filter(([k]) => k !== "updated_at")));
  expect(strip(after)).toEqual(strip(before));
});

test("reset username and password keeps transactions", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  const dialogs = acceptDialogs(page);
  await openSettings(page);
  await page.getByLabel("New username").fill("renamed-user");
  await page.getByLabel("New password").fill("another-password-456");
  await page.getByRole("button", { name: "Update" }).click();
  await expect(page.getByText("Credentials updated successfully.")).toBeVisible();
  expect(dialogs[0]).toContain("keep existing transactions");

  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/login$/);
  const old = await page.request.post("/api/login", { data: { username: USER, password: PASSWORD } });
  expect(old.status()).toBe(401);
  await loginViaUi(page, "renamed-user", "another-password-456");
  expect(await listTx(page.request)).toHaveLength(6);
});

test("delete all transactions asks first", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await openSettings(page);
  page.once("dialog", (d) => void d.dismiss());
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  expect(await listTx(page.request)).toHaveLength(6);

  page.once("dialog", (d) => {
    expect(d.message()).toBe("Delete ALL transactions? This cannot be undone.");
    void d.accept();
  });
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByText("All transactions deleted.")).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(0);
});

test("encrypted backup downloads and restores", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  const before = await listTx(page.request);
  acceptDialogs(page, "backup-secret");
  await openSettings(page);

  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download" }).click();
  const d = await download;
  expect(d.suggestedFilename()).toBe("bitcoin_backup.btx");
  const backup = (await d.path())!;
  await expect(page.getByText("Backup downloaded.")).toBeVisible();

  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page.getByText("All transactions deleted.")).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(0);

  // A wrong password is refused and changes nothing.
  await page.getByLabel("Backup file").setInputFiles(backup);
  await page.getByLabel("Backup password").fill("wrong");
  await page.getByRole("button", { name: "Restore" }).click();
  await expect(page.getByText("Failed to restore backup.")).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(0);

  await page.getByLabel("Backup file").setInputFiles(backup);
  await page.getByLabel("Backup password").fill("backup-secret");
  await page.getByRole("button", { name: "Restore" }).click();
  await expect(page).toHaveURL(/\/login$/, { timeout: 15_000 });
  await loginViaUi(page);
  const after = await listTx(page.request);
  expect(after.map((t) => t.id)).toEqual(before.map((t) => t.id));
  expect(after.map((t) => t.realized_gain_usd)).toEqual(before.map((t) => t.realized_gain_usd));
});

test("a blank backup password cancels", async ({ authedPage: page }) => {
  acceptDialogs(page, "");
  await openSettings(page);
  await page.getByRole("button", { name: "Download" }).click();
  await expect(page.getByText("Backup canceled.")).toBeVisible();
});

test("export as CSV", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await openSettings(page);
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export CSV" }).click();
  const d = await download;
  expect(d.suggestedFilename()).toMatch(/\.csv$/);
  const text = readFileSync((await d.path())!, "utf8");
  const lines = text.trim().split(/\r?\n/);
  expect(lines).toHaveLength(7); // header + 6 transactions
  expect(lines[0]).toMatch(/date/i);
  expect(text).toContain("Transfer");
});

test("connect an AI assistant: prompt and configs name this server and user", async ({ authedPage: page, context, baseURL }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await openSettings(page);
  await expect(page.getByRole("heading", { name: "Connect an AI Assistant" })).toBeVisible();
  const prompt = page.getByLabel("Setup prompt");
  await expect(prompt).toHaveValue(new RegExp(baseURL!.replace(/[.:/]/g, "\\$&")));
  await expect(prompt).toHaveValue(new RegExp(USER));
  const promptBlock = page.getByRole("button", { name: "Copy" }).first();
  await promptBlock.click();
  await expect(page.getByText("Setup prompt copied.")).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(await prompt.inputValue());

  await page.getByText("Set it up yourself").click();
  await expect(page.getByLabel("Claude Desktop config")).toHaveValue(/btctx/i);
  await expect(page.getByLabel("Claude Code command")).toHaveValue(/claude mcp add/);
});
