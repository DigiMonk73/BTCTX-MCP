// Settings: timezone, recalculation, credentials, delete, backup and
// restore, CSV export, Ledger Review, Privacy & Network, the Connect an AI
// Assistant prompt, and About BitcoinTX.
import {
  test, expect, seedKnownLedger, createTx, listTx, loginViaUi, acceptDialogs, python, USER, PASSWORD, REPO,
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
  await expect(page.getByRole("region", { name: "Account" }).getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  expect((await historyCsv(page, 2024)).match(/Sell/g)).toHaveLength(2);

  await select.selectOption("Asia/Tokyo");
  await page.getByRole("region", { name: "Account" }).getByRole("button", { name: "Save", exact: true }).click();
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
  // The current password is needed, and checked by the server.
  await page.getByRole("button", { name: "Update" }).click();
  await expect(page.getByText("Enter your current password")).toBeVisible();
  await page.getByLabel("Current password").fill("not-the-password");
  await page.getByRole("button", { name: "Update" }).click();
  await expect(page.getByText("Current password is incorrect.")).toBeVisible();
  await page.getByLabel("Current password").fill(PASSWORD);
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
  acceptDialogs(page); // the "Delete ALL transactions?" confirm below
  await openSettings(page);
  // Privacy audit 2026-09-29 (3d): the plain safety copies are mentioned
  await expect(page.getByText("unencrypted safety copies")).toBeVisible();

  const download = page.waitForEvent("download");
  await page.getByLabel("Encrypt with password").fill("backup-secret");
  await page.getByLabel("Repeat password").fill("backup-secret");
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

test("the backup password is hidden and must be typed twice alike", async ({ authedPage: page }) => {
  // Privacy audit 2026-09-29 (3b), owner decision: it was a plain pop-up,
  // shown as typed and asked once, so a typo made a backup no one could open.
  let downloads = 0;
  page.on("download", () => downloads++);
  await openSettings(page);
  await expect(page.getByLabel("Encrypt with password")).toHaveAttribute("type", "password");
  await expect(page.getByLabel("Repeat password")).toHaveAttribute("type", "password");
  await page.getByLabel("Encrypt with password").fill("backup-secret");
  await page.getByLabel("Repeat password").fill("backup-secreT");
  await page.getByRole("button", { name: "Download" }).click();
  await expect(page.getByText("The two passwords don't match.")).toBeVisible();
  expect(downloads).toBe(0);
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

  // How to update an AI app set up for an older version
  const version = readFileSync(path.join(REPO, "VERSION"), "utf8").trim();
  await expect(ai.getByText("Set up with an older version?")).toContainText(`btctx-mcp==${version}`);

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

test("ledger review: a My BTC deposit without its original date is a folded reminder (#128)", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  const mine = await createTx(page.request, {
    type: "Deposit", timestamp: "2024-06-01T15:00:00Z", from_account_id: 99, to_account_id: 2,
    amount: "0.01", cost_basis_usd: "500", fee_amount: "0", fee_currency: "BTC", source: "MyBTC",
  });
  await openSettings(page);
  const review = page.getByRole("region", { name: "Ledger review" });
  const title = "Reminder: My BTC and Gift deposits counted from their deposit date";
  await expect(review.getByText("Nothing looks wrong.")).toBeVisible();
  await expect(review.getByText(`${title}: 1`)).toBeVisible();
  await expect(review.getByText(/change their Source instead/)).toBeVisible();
  const list = review.getByRole("list", { name: title });
  await expect(list).toHaveCount(0);
  await review.getByRole("button", { name: "Show the 1 deposit" }).click();
  await expect(list).toContainText(`#${mine.id} · `);
  await expect(list).toContainText("Deposit (MyBTC) · 0.01000000 BTC");
  await review.getByRole("button", { name: "Hide the list" }).click();
  await expect(list).toHaveCount(0);
});

test("ledger review prices a day-valued fee again after asking (#144)", async ({ app, authedPage: page }) => {
  await seedKnownLedger(page.request); // its transfer fee: 0.0001 x $50,000 = $5.00, at the day (no hourly prices here)
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
  const title = "Values priced at the day's price that the hour would change";
  await expect(review.getByText(`${title}: 1`)).toBeVisible();
  const item = review.getByRole("listitem").filter({ hasText: `#${transfer.id} · ` });
  await expect(item).toContainText("Fee value $6.00 -> $5.00.");
  const apply = review.getByRole("button", { name: "Apply to the ticked ones" });
  await expect(apply).toBeDisabled();
  await item.getByRole("checkbox").check();
  // A refused apply says so, and stays said after the review reloads
  await page.route("**/api/review/hourly-prices", (route) => route.fulfill({ status: 500, body: "{}" }),
    { times: 1 });
  await apply.click();
  await expect(review.getByText(/^The apply failed, or its answer didn't arrive/)).toBeVisible();
  expect(await listTx(page.request)).toContainEqual(expect.objectContaining({ id: transfer.id, fee_usd: "6.00" }));
  await apply.click();
  await expect(review.getByText(/^Changed 1 transaction and recalculated the ledger; the copy from before is backups\//))
    .toBeVisible();
  await expect(review.getByText("Nothing to review.")).toBeVisible();
  expect(dialogs[1]).toContain("Change the 1 ticked transaction to the values shown");
  const fixed = (await listTx(page.request)).find((t) => t.id === transfer.id)!;
  expect(fixed.fee_usd).toBe("5.00");
});

test("privacy & network: the price card, its fields and errors; Nobody shows on the dashboard", async ({
  authedPage: page,
}) => {
  await openSettings(page);
  const net = page.getByRole("region", { name: "Privacy & network" });
  const save = net.getByRole("button", { name: "Save" });
  await expect(net.getByLabel(/^Public price sites/)).toBeChecked();
  await expect(save).toBeDisabled();

  // Through Tor: its address, prefilled; a bad one is refused under the field (and in a toast)
  await net.getByLabel("Through Tor").check();
  await expect(net.getByLabel("Tor's address")).toHaveValue("socks5h://127.0.0.1:9050");
  await net.getByLabel("Tor's address").fill("ftp://127.0.0.1:9050");
  await save.click();
  await expect(net.locator(".field-error")).toHaveText(/The proxy must look like socks5:\/\/host:port/);
  await expect(net.getByLabel("Tor's address")).toHaveAttribute("aria-invalid", "true");

  // My own Mempool: its address (needed to save) and the backup; Tor only with the backup
  await net.getByLabel(/^My own Mempool/).check();
  await expect(net.getByLabel("If it can't answer, ask public price sites")).not.toBeChecked();
  await expect(net.getByLabel("Through Tor")).toHaveCount(0);
  await expect(save).toBeDisabled();
  await expect(net.getByText("Enter your Mempool's address.")).toBeVisible();
  await net.getByLabel("Your Mempool's address").fill("http://127.0.0.1:9");
  await net.getByLabel("If it can't answer, ask public price sites").check();
  await net.getByLabel("Tor's address").fill("socks5h://127.0.0.1:9050");
  await save.click();
  await expect(page.getByText("Price source saved.")).toBeVisible();
  expect(await (await page.request.get("/api/settings/network")).json()).toEqual({
    price_source: "mempool", mempool_url: "http://127.0.0.1:9", mempool_fallback: true,
    proxy_url: "socks5h://127.0.0.1:9050", managed: false, invalid: false, waiting: false, tor_from_server: false,
    host: "server",
    confirmed: true, chosen_at: expect.stringMatching(/Z$/), chosen_via: "settings",
  });

  await net.getByLabel(/^Nobody/).check();
  await expect(net.getByLabel("Your Mempool's address")).toHaveCount(0);
  await save.click();
  await expect(page.getByText("Price source saved.").last()).toBeVisible();
  await expect(net.getByRole("status")).toContainText("Fully offline: nothing is contacted.");
  await page.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.locator(".btc-price-value")).toHaveText("Offline"); // the price card
});

test.describe("a fresh install asks where prices come from", () => {
  test.use({ priceSource: "unset" });

  test("on the Dashboard only, nothing chosen until the owner picks; saved with no reload (#149)", async ({
    authedPage: page, browserName,
  }) => {
    const card = page.getByRole("region", { name: "Bitcoin prices" });
    await expect(card).toBeVisible();
    await expect(card.getByRole("status")).toHaveText(/Not chosen yet: nothing is contacted\./);
    // the hourly history: where it will come from, and that nothing in it names a date (#145)
    await expect(card).toContainText("downloaded once from Bitstamp when you choose Public price sites");
    await expect(card).toContainText("Nothing in the download names your dates.");
    await expect(page.locator(".btc-price-value")).toHaveText("Not chosen yet"); // the dashboard asked nothing
    expect((await (await page.request.get("/api/settings/network")).json()).price_source).toBe("unset");
    // #149: a reload before choosing, and one after. Playwright's WebKit crashes
    // at the next navigation after any reload of a signed-in page, with or
    // without this card (#149 checks Safari and the Mac app by hand): there,
    // only the one after
    if (browserName !== "webkit") await page.reload();
    const use = card.getByRole("button", { name: "Use this" });
    await expect(use).toBeDisabled();
    await card.getByLabel(/^My own Mempool/).check();
    await expect(use).toBeDisabled(); // needs its address
    await expect(card).toContainText("It has hourly prices only from when it began recording.");
    await card.getByLabel(/^Public price sites/).check();
    let loads = 0;
    page.on("load", () => (loads += 1));
    await use.click();
    await expect(card).toHaveCount(0);
    await expect(page.locator(".btc-price-value")).toHaveText(/^\$/); // asked again, in place
    expect(loads).toBe(0);
    expect((await (await page.request.get("/api/settings/network")).json()).price_source).toBe("public");
    await page.reload();
    await expect(page.getByRole("region", { name: "Bitcoin prices" })).toHaveCount(0);
    await openSettings(page);
    await expect(page.getByRole("region", { name: "Privacy & network" }).getByLabel(/^Public price sites/)).toBeChecked();
  });
});

test.describe("prices set by StartOS", () => {
  test.use({ priceSource: "startos" });

  test("Settings shows them read-only, in words, and the first-run question never appears", async ({
    authedPage: page,
  }) => {
    await expect(page.getByRole("region", { name: "Bitcoin prices" })).toHaveCount(0);
    await openSettings(page);
    const net = page.getByRole("region", { name: "Privacy & network" });
    await expect(net.getByText("Set in StartOS. To change it: BitcoinTX › Actions › Price Source & Privacy.")).toBeVisible();
    const chosen = net.locator(".price-choice.chosen");
    await expect(chosen).toContainText("My own Mempool");
    await expect(chosen).toContainText("✓ Chosen");
    await expect(chosen).toContainText("Mempool on this server");
    await expect(net).not.toContainText("10.0.3.1"); // StartOS's internal address isn't for people
    await expect(net.getByRole("radio")).toHaveCount(0);
    await expect(net.getByRole("button", { name: "Save" })).toHaveCount(0);
    const r = await page.request.put("/api/settings/network", { data: { price_source: "public" } });
    expect(r.status()).toBe(409);
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

test("About BitcoinTX shows the version and where to report a problem", async ({ authedPage: page }) => {
  await openSettings(page);
  const about = page.getByRole("region", { name: "About BitcoinTX" });
  const version = readFileSync(path.join(REPO, "VERSION"), "utf8").trim();
  await expect(about.getByText(`Version ${version}`)).toBeVisible();
  // The one-wallet notice and the disclaimer, worded as everywhere else
  await expect(about.getByRole("note")).toContainText(
    "Important: one wallet, one exchange. BitcoinTX tracks one self-custody wallet and one exchange account.");
  await expect(about.getByText("BitcoinTX is software, not tax, legal or financial advice.")).toBeVisible();
  const github = "https://github.com/DigiMonk73/BTCTX-MCP";
  for (const [name, href] of [
    ["Report a problem", `${github}/issues/new/choose`],
    ["open bugs", `${github}/issues?q=is%3Aissue+is%3Aopen+label%3Abug`],
    ["Report it privately", `${github}/security/advisories/new`],
    ["release notes", `${github}/releases`],
  ]) {
    const link = about.getByRole("link", { name, exact: true });
    await expect(link).toHaveAttribute("href", href);
    await expect(link).toHaveAttribute("target", "_blank");
  }
});
