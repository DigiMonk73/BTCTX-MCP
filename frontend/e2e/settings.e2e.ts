// Settings: timezone, recalculation, credentials, delete, backup and
// restore, CSV export, and the Connect an AI Assistant prompt.
import {
  test, expect, seedKnownLedger, createTx, listTx, loginViaUi, acceptDialogs, python, USER, PASSWORD,
} from "./fixtures";
import { request as playwrightRequest, type Page } from "@playwright/test";
import { readFileSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import path from "node:path";

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

test("connect an AI assistant: prompt and configs name this server and user", async ({ authedPage: page, context, baseURL, browserName }) => {
  // WebKit has no clipboard permissions to grant; read the clipboard back in Chromium only.
  const canReadClipboard = browserName === "chromium";
  if (canReadClipboard) await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await openSettings(page);
  await expect(page.getByRole("heading", { name: "Connect an AI Assistant" })).toBeVisible();
  const prompt = page.getByLabel("Setup prompt");
  await expect(prompt).toHaveValue(new RegExp(baseURL!.replace(/[.:/]/g, "\\$&")));
  await expect(prompt).toHaveValue(new RegExp(USER));
  const promptBlock = page.getByRole("button", { name: "Copy" }).first();
  await promptBlock.click();
  await expect(page.getByText("Setup prompt copied.")).toBeVisible();
  if (canReadClipboard) {
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(await prompt.inputValue());
  }

  await page.getByText("Set it up yourself").click();
  await expect(page.getByLabel("Claude Desktop config")).toHaveValue(/btctx/i);
  await expect(page.getByLabel("Claude Code command")).toHaveValue(/claude mcp add/);
});

test.describe("Mac app: AI assistant key instead of a password", () => {
  test.use({ appMode: "mac" });

  test("key file, access switch, reset, and a setup with no secrets", async ({ authedPage: page, app }) => {
    const keyFile = path.join(app.dir, "mcp.json");
    const first = JSON.parse(readFileSync(keyFile, "utf8"));
    expect(first.url).toBe(app.url);
    expect(statSync(keyFile).mode & 0o777).toBe(0o600);

    await openSettings(page);
    const ai = page.getByRole("region", { name: "Connect an AI Assistant" });
    const prompt = ai.getByLabel("Setup prompt");
    await expect(prompt).toHaveValue(/finds it by itself/);
    for (const secret of ["BTCTX_PASSWORD", "BTCTX_USERNAME", "BTCTX_URL", USER]) {
      await expect(prompt).not.toHaveValue(new RegExp(secret));
    }
    await ai.getByText("Set it up yourself").click();
    await expect(ai.getByLabel("Grok Build command")).toHaveValue(/^grok mcp add bitcointx -- uvx/);
    await expect(ai.getByLabel("Claude Code command")).not.toHaveValue(/-e /);

    const key = { Authorization: `Bearer ${first.token}` };
    const anon = await playwrightRequest.newContext({ baseURL: app.url });
    expect((await anon.get("/api/transactions", { headers: key })).status()).toBe(200);

    const toggle = ai.getByLabel("Let AI assistants use BitcoinTX");
    await expect(toggle).toBeChecked();
    await toggle.uncheck();
    await expect(page.getByText("AI assistant access is off.")).toBeVisible();
    expect((await anon.get("/api/transactions", { headers: key })).status()).toBe(401);
    await toggle.check();
    await expect(page.getByText("AI assistants can use BitcoinTX.")).toBeVisible();

    acceptDialogs(page);
    await ai.getByRole("button", { name: "Reset key" }).click();
    await expect(page.getByText("AI assistant key reset.")).toBeVisible();
    const second = JSON.parse(readFileSync(keyFile, "utf8"));
    expect(second.token).not.toBe(first.token);
    expect((await anon.get("/api/transactions", { headers: key })).status()).toBe(401);
    const newKey = { Authorization: `Bearer ${second.token}` };
    expect((await anon.get("/api/transactions", { headers: newKey })).status()).toBe(200);
    await anon.dispose();
  });
});

test("server installs keep the username/password setup and no key controls", async ({ authedPage: page }) => {
  await openSettings(page);
  const ai = page.getByRole("region", { name: "Connect an AI Assistant" });
  await expect(ai.getByLabel("Setup prompt")).toHaveValue(/BTCTX_PASSWORD: don't ask me for it/);
  await expect(ai.getByLabel("Let AI assistants use BitcoinTX")).toHaveCount(0);
  await expect(ai.getByRole("button", { name: "Reset key" })).toHaveCount(0);
});

test("ledger review lists a $0 spend and changes nothing", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  await openSettings(page);
  const review = page.getByRole("region", { name: "Ledger review" });
  await expect(review.getByText("Nothing to review.")).toBeVisible();

  const spend = await createTx(page.request, {
    type: "Withdrawal", timestamp: "2024-06-01T15:00:07Z", from_account_id: 2, to_account_id: 99,
    amount: "0.01", proceeds_usd: "0", fee_amount: "0", fee_currency: "BTC", purpose: "Spent",
  });
  const before = await listTx(page.request);
  await review.getByRole("button", { name: "Check again" }).click();
  const list = review.getByRole("list", { name: "Spent withdrawals saved with $0 proceeds" });
  await expect(list.getByRole("listitem")).toHaveCount(1);
  await expect(list).toContainText(`#${spend.id} · `);
  await expect(list).toContainText("Withdrawal (Spent) · 0.01000000 BTC");
  expect(await listTx(page.request)).toEqual(before);
});

test("ledger review fixes a live-priced transfer fee after asking", async ({ app, authedPage: page }) => {
  await seedKnownLedger(page.request); // its transfer fee: 0.0001 x $50,000 = $5.00
  const transfer = (await listTx(page.request)).find((t) => t.type === "Transfer")!;
  // As an older version saved it when the day's lookup failed: at the live price.
  execFileSync(python(), ["-c",
    "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); " +
    "c.execute('UPDATE transactions SET fee_usd=6.00 WHERE id=?', (int(sys.argv[2]),)); c.commit()",
    path.join(app.dir, "e2e.db"), String(transfer.id)]);
  await page.request.post("/api/transactions/recalculate");

  const dialogs = acceptDialogs(page);
  await openSettings(page);
  const review = page.getByRole("region", { name: "Ledger review" });
  const title = "Transfer fees valued far from that day's price (probably at the live price)";
  await expect(review.getByRole("list", { name: title })).toContainText("$6.00 -> $5.00");
  await review.getByRole("button", { name: "Fix these" }).click();
  await expect(review.getByText("Nothing to review.")).toBeVisible();
  expect(dialogs[0]).toContain("Set 1 transfer fee value(s) to that day's BTC price");
  const fixed = (await listTx(page.request)).find((t) => t.id === transfer.id)!;
  expect(fixed.fee_usd).toBe("5.00");
});
