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
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  expect((await historyCsv(page, 2024)).match(/Sell/g)).toHaveLength(2);

  await select.selectOption("Asia/Tokyo");
  await page.getByRole("button", { name: "Save", exact: true }).click();
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

test("connect an AI assistant: prompt and configs name this server, never a password", async ({ authedPage: page, context, baseURL, browserName }) => {
  // WebKit has no clipboard permissions to grant; read the clipboard back in Chromium only.
  const canReadClipboard = browserName === "chromium";
  if (canReadClipboard) await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await openSettings(page);
  await expect(page.getByRole("heading", { name: "Connect an AI Assistant" })).toBeVisible();
  // The privacy warning comes before the setup prompt.
  const ai = page.getByRole("region", { name: "Connect an AI Assistant" });
  await expect(ai.getByRole("note")).toContainText("Your data goes to the AI's model.");
  await expect(ai.getByRole("note")).toContainText("local model");
  const prompt = page.getByLabel("Setup prompt");
  await expect(prompt).toHaveValue(new RegExp(baseURL!.replace(/[.:/]/g, "\\$&")));
  await expect(prompt).toHaveValue(/BTCTX_AI_KEY: don't ask me for it/);
  for (const secret of ["BTCTX_PASSWORD", "BTCTX_USERNAME", USER, PASSWORD]) {
    await expect(prompt).not.toHaveValue(new RegExp(secret));
  }
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

test.describe("Mac app: AI key file instead of a password", () => {
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

    // Off until the owner turns it on.
    const key = { Authorization: `Bearer ${first.token}` };
    const anon = await playwrightRequest.newContext({ baseURL: app.url });
    const toggle = ai.getByLabel("Let AI assistants use BitcoinTX");
    await expect(toggle).not.toBeChecked();
    await expect(ai.getByText(/Turn on AI access above first\./)).toBeVisible();
    // The Mac app resets its key file; no Create/Revoke here.
    await expect(ai.getByRole("button", { name: "Create AI key" })).toHaveCount(0);
    expect((await anon.get("/api/transactions", { headers: key })).status()).toBe(401);
    await toggle.check();
    await expect(page.getByText("AI assistants can use BitcoinTX.")).toBeVisible();
    expect((await anon.get("/api/transactions", { headers: key })).status()).toBe(200);
    await toggle.uncheck();
    await expect(page.getByText("AI access is off.")).toBeVisible();
    expect((await anon.get("/api/transactions", { headers: key })).status()).toBe(401);
    await toggle.check();
    // The first "on" toast may still be showing: check the newest.
    await expect(page.getByText("AI assistants can use BitcoinTX.").last()).toBeVisible();

    acceptDialogs(page);
    await ai.getByRole("button", { name: "Reset key" }).click();
    await expect(page.getByText("AI key reset.")).toBeVisible();
    const second = JSON.parse(readFileSync(keyFile, "utf8"));
    expect(second.token).not.toBe(first.token);
    expect((await anon.get("/api/transactions", { headers: key })).status()).toBe(401);
    const newKey = { Authorization: `Bearer ${second.token}` };
    expect((await anon.get("/api/transactions", { headers: newKey })).status()).toBe(200);
    await anon.dispose();
  });
});

test("Docker/StartOS: create, replace and revoke the AI key; it's shown once", async ({ authedPage: page, app }) => {
  await openSettings(page);
  const ai = page.getByRole("region", { name: "Connect an AI Assistant" });
  const anon = await playwrightRequest.newContext({ baseURL: app.url });
  const works = async (key: string) =>
    (await anon.get("/api/transactions", { headers: { Authorization: `Bearer ${key}` } })).status();
  await expect(ai.getByRole("button", { name: "Reset key" })).toHaveCount(0);
  const toggle = ai.getByLabel("Let AI assistants use BitcoinTX");
  await expect(toggle).not.toBeChecked();

  // Create: shown once, with a warning while access is still off.
  await ai.getByRole("button", { name: "Create AI key" }).click();
  const shown = ai.getByRole("group", { name: "New AI key" });
  await expect(shown).toContainText("only time BitcoinTX shows this key");
  await expect(shown).toContainText("turn on AI access");
  const first = await shown.getByLabel("AI key").inputValue();
  expect(first).toMatch(/^btctx_ak_/);
  expect(await works(first)).toBe(401); // access is off
  await toggle.check();
  await expect(page.getByText("AI assistants can use BitcoinTX.")).toBeVisible();
  expect(await works(first)).toBe(200);
  // The key can't reach login-only actions.
  const restore = await anon.post("/api/backup/restore", {
    headers: { Authorization: `Bearer ${first}` }, multipart: { password: "x", file: { name: "b.btx", mimeType: "application/octet-stream", buffer: Buffer.from("x") } },
  });
  expect(restore.status()).toBe(403);

  // Leaving the page forgets it: a reload shows no key.
  await page.reload();
  await openSettings(page);
  await expect(ai.getByRole("group", { name: "New AI key" })).toHaveCount(0);
  await expect(page.getByText(first)).toHaveCount(0);

  // New key replaces the old one.
  acceptDialogs(page);
  await ai.getByRole("button", { name: "New key" }).click();
  const second = await ai.getByRole("group", { name: "New AI key" }).getByLabel("AI key").inputValue();
  expect(second).not.toBe(first);
  expect(await works(first)).toBe(401);
  expect(await works(second)).toBe(200);

  // Switch off: refused with the reason; back on: works again.
  await toggle.uncheck();
  await expect(page.getByText("AI access is off.")).toBeVisible();
  const off = await anon.get("/api/transactions", { headers: { Authorization: `Bearer ${second}` } });
  expect(off.status()).toBe(401);
  expect((await off.json()).detail).toBe("AI access is turned off in BitcoinTX Settings.");
  await toggle.check();

  // Revoke.
  await ai.getByRole("button", { name: "Revoke" }).click();
  await expect(page.getByText("AI key revoked.")).toBeVisible();
  expect(await works(second)).toBe(401);
  await expect(ai.getByRole("button", { name: "Create AI key" })).toBeVisible();
  await anon.dispose();
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

test("privacy & network: price source, mempool fallback, proxy; off shows on the dashboard", async ({ authedPage: page }) => {
  await openSettings(page);
  const net = page.getByRole("region", { name: "Privacy & network" });
  const save = net.getByRole("button", { name: "Save privacy & network settings" });
  const source = net.getByLabel("Price source");
  await expect(source).toHaveValue("public");
  await expect(save).toBeDisabled();

  await net.getByLabel("Proxy for public sites").fill("ftp://127.0.0.1:9050");
  await save.click();
  await expect(page.getByText(/The proxy must look like socks5:\/\/host:port/)).toBeVisible();

  // My mempool: its address and the fallback switch appear.
  await source.selectOption("mempool");
  await expect(net.getByLabel("Fall back to public price sites")).not.toBeChecked();
  await net.getByLabel("Proxy for public sites").fill("socks5h://127.0.0.1:9050");
  await save.click();
  await expect(page.getByText("Enter your mempool server's address to use it.")).toBeVisible();
  await net.getByLabel("Your mempool server").fill("http://127.0.0.1:9");
  await net.getByLabel("Fall back to public price sites").check();
  await save.click();
  await expect(page.getByText("Privacy & network settings saved.")).toBeVisible();
  expect(await (await page.request.get("/api/settings/network")).json()).toEqual({
    price_source: "mempool", mempool_url: "http://127.0.0.1:9", mempool_fallback: true,
    proxy_url: "socks5h://127.0.0.1:9050",
  });

  await source.selectOption("off");
  await expect(net.getByLabel("Your mempool server")).toHaveCount(0);
  await save.click();
  await expect(page.getByText("Privacy & network settings saved.").last()).toBeVisible();
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByText("Prices off")).toBeVisible();
});

test.describe("a fresh install asks where prices come from", () => {
  test.use({ priceSource: "unset" });

  test("nothing is chosen until the owner picks; the question then goes away", async ({ authedPage: page }) => {
    const prompt = page.getByRole("region", { name: "Choose a price source" });
    await expect(prompt).toBeVisible();
    await expect(page.getByText("Prices off")).toBeVisible(); // the dashboard asked nothing
    expect((await (await page.request.get("/api/settings/network")).json()).price_source).toBe("unset");
    const use = prompt.getByRole("button", { name: "Use this" });
    await expect(use).toBeDisabled();
    await prompt.getByLabel(/My mempool server/).check();
    await expect(use).toBeDisabled(); // needs its address
    await prompt.getByLabel(/Public price sites/).check();
    await use.click();
    await expect(prompt).toHaveCount(0);
    expect((await (await page.request.get("/api/settings/network")).json()).price_source).toBe("public");
    await openSettings(page);
    await expect(page.getByRole("region", { name: "Privacy & network" }).getByLabel("Price source")).toHaveValue("public");
  });
});

test("settings rows: text fields sit under their text, and no control rises above its row", async ({ authedPage: page }) => {
  await openSettings(page);
  const textField = 'input:not([type]), input[type="text"], input[type="url"], input[type="password"], textarea';
  // Desktop, the tablet sidebar layout, and a phone.
  for (const width of [1280, 960, 390]) {
    await page.setViewportSize({ width, height: 900 });
    const problems = await page.locator(".settings-option").evaluateAll((rows, textField) =>
      rows.flatMap((row) => {
        const title = row.querySelector(".settings-option-title");
        if (!title) return [];
        const name = title.textContent?.trim();
        const texts = [title, row.querySelector(".settings-option-subtitle")].filter((t) => t !== null);
        const out: string[] = [];
        for (const t of texts) {
          if (t.scrollWidth > t.clientWidth + 1) out.push(`${name}: text squeezed into ${t.clientWidth}px`);
        }
        const titleTop = title.getBoundingClientRect().top;
        const textBottom = Math.max(...texts.map((t) => t.getBoundingClientRect().bottom));
        for (const control of Array.from(row.querySelectorAll("input, select, textarea, button"))) {
          const box = control.getBoundingClientRect();
          if (!box.width && !box.height) continue; // inside a closed <details>
          const label = control.getAttribute("aria-label") || control.id || control.textContent?.trim();
          if (box.top < titleTop - 1) out.push(`${name}: "${label}" starts above the title`);
          if (control.matches(textField) && box.top < textBottom - 1) out.push(`${name}: "${label}" is beside or over the text`);
        }
        return out;
      }), textField);
    expect(problems, `at ${width}px wide`).toEqual([]);
  }
});
