// Shared fixtures: every test gets its own backend on a fresh temp database
// (scripts/smoke_test.py --serve: historical BTC price $50,000, current
// $60,000, block height 900,000), so tests never depend on each other.
// Those prices are stubbed, or with `fakeInternet` come from a fake internet.
import { test as base, expect, type Page, type APIRequestContext, type APIResponse } from "@playwright/test";
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export const REPO = path.resolve(__dirname, "..", "..");
export const USER = "e2e-user";
export const PASSWORD = "e2e-password-123";
export const HISTORICAL_PRICE = 50000;
export const CURRENT_PRICE = 60000;

export function python(): string {
  if (process.env.BTCTX_PYTHON) return process.env.BTCTX_PYTHON;
  for (const c of [".venv/bin/python", "desktop/.venv/bin/python"]) {
    if (existsSync(path.join(REPO, c))) return path.join(REPO, c);
  }
  return "python3";
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const srv = net.createServer();
    srv.listen(0, "127.0.0.1", () => {
      const port = (srv.address() as net.AddressInfo).port;
      srv.close(() => resolve(port));
    });
    srv.on("error", reject);
  });
}

export interface App {
  url: string;
  dir: string;
}

async function startApp(
  extraEnv: (dir: string, port: number) => Record<string, string>,
): Promise<{ app: App; proc: ChildProcess; log: string[] }> {
  const dir = mkdtempSync(path.join(os.tmpdir(), "btctx-e2e-"));
  const port = await freePort();
  const log: string[] = [];
  const proc = spawn(
    python(),
    ["scripts/smoke_test.py", "--serve", String(port), path.join(dir, "e2e.db")],
    { cwd: REPO, env: { ...process.env, PYTHONUNBUFFERED: "1", ...extraEnv(dir, port) } },
  );
  proc.stdout?.on("data", (d) => log.push(String(d)));
  proc.stderr?.on("data", (d) => log.push(String(d)));
  const url = `http://127.0.0.1:${port}`;
  for (let i = 0; i < 120; i++) {
    if (proc.exitCode !== null) {
      throw new Error(`server exited early (${proc.exitCode}):\n${log.join("")}`);
    }
    try {
      const r = await fetch(`${url}/api/health`);
      if (r.ok) return { app: { url, dir }, proc, log };
    } catch {
      // not up yet
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  proc.kill();
  throw new Error(`server did not start:\n${log.join("")}`);
}

/** Where the server logs its requests to outside services (fakeInternet). */
const OUTSIDE_LOG = "outside-requests.jsonl";

export interface OutsideRequest {
  url: string;
  /** The proxy it was sent through, or null for a direct request. */
  proxy: string | null;
}

/**
 * A past day's price from the fake internet (fakeInternet): $50,000 plus the
 * day's number mod 100, so the day before or after shows a different figure
 * (smoke_test.py, fake_past_price). `day` is YYYY-MM-DD.
 */
export function fakePastPrice(day: string): number {
  return HISTORICAL_PRICE + (Date.parse(`${day}T00:00:00Z`) / 86_400_000) % 100;
}

/** What the server sent to outside services so far (with fakeInternet), oldest first. */
export function outsideRequests(app: App): OutsideRequest[] {
  const file = path.join(app.dir, OUTSIDE_LOG);
  if (!existsSync(file)) return [];
  return readFileSync(file, "utf8").split("\n").filter(Boolean).map((line) => JSON.parse(line));
}

/**
 * The first-run setup code the server wrote next to its database (outside
 * the Mac app, while the account has the default login), or undefined.
 */
export function setupCode(app: App): string | undefined {
  const file = path.join(app.dir, "setup-code.txt");
  return existsSync(file) ? readFileSync(file, "utf8").trim() : undefined;
}

/** Claim the default account over the API (the UI flow has its own test). */
export async function claimAccount(request: APIRequestContext, app: App) {
  const r = await request.post("/api/users/reset-account", {
    data: { username: USER, password: PASSWORD, setup_code: setupCode(app) },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
}

/** Log in through the login form, as a user would. */
export async function loginViaUi(page: Page, user = USER, password = PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("Username").fill(user);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log In" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}

/** A price choice as Settings › Privacy & network saves it. */
export type PriceChoice = {
  price_source: "off" | "public" | "mempool";
  mempool_url?: string;
  mempool_fallback?: boolean;
  proxy_url?: string;
};

/** Sent on window by the price card once it has saved a choice (usePriceCard.ts). */
export const PRICE_CHOICE_SAVED = "btctx:price-choice-saved";

/**
 * Save a price choice over the API, as Settings › Privacy & network does,
 * then tell the open page as the card does: the Dashboard and the sidebar
 * ask again in place. No page load: the app needs none for a new choice
 * (#149), and Playwright's WebKit now and then fails the navigation that
 * follows such a save with "WebKit encountered an internal error" (#231).
 * Needs a signed-in page with the sidebar showing (not a phone's width):
 * it waits for the sidebar's price first.
 */
export async function choosePriceSource(page: Page, choice: PriceChoice) {
  // The sidebar's answer for the old choice first: one arriving after the new one would replace it
  await expect(page.getByRole("complementary").getByText(/^BTC Price: [^…]/)).toBeVisible();
  const r = await page.request.put("/api/settings/network", {
    data: { mempool_url: null, mempool_fallback: false, proxy_url: null, ...choice },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
  await page.evaluate((event) => window.dispatchEvent(new Event(event)), PRICE_CHOICE_SAVED);
}

export type TxPayload = Record<string, string | number | null>;

/** Create a transaction over the API, confirming the past-year warning (sendConfirmed); returns the saved record. */
export async function createTx(request: APIRequestContext, data: TxPayload) {
  const r = await sendConfirmed((params) => request.post("/api/transactions", { data, params }));
  expect(r.ok(), await r.text()).toBeTruthy();
  return r.json();
}

/**
 * A write over the API through 2.0's past-year warning (docs/temp/2.0-accounts.md 5.8): the tests' rows are
 * dated in earlier tax years, and no switch turns the warning off on a running server, so a 409 that gives a
 * fingerprint (`confirm`) is sent again, once, with ?confirm=<it>. The answer either way: a second 409 (the
 * ledger changed meanwhile) is the caller's to check.
 */
export async function sendConfirmed(
  send: (params?: { confirm: string }) => Promise<APIResponse>,
): Promise<APIResponse> {
  const r = await send();
  const fingerprint = await fingerprintAsked(r);
  return fingerprint === undefined ? r : send({ confirm: fingerprint });
}

/** The `confirm` of the warning's 409; undefined for any other answer (Delete All's 409 asks for a typed DELETE). */
async function fingerprintAsked(r: APIResponse): Promise<string | undefined> {
  if (r.status() !== 409) return undefined;
  const body: unknown = await r.json().catch(() => undefined);
  const confirm = body !== null && typeof body === "object" ? (body as { confirm?: unknown }).confirm : undefined;
  return typeof confirm === "string" ? confirm : undefined;
}

export async function listTx(request: APIRequestContext) {
  const r = await request.get("/api/transactions");
  expect(r.ok()).toBeTruthy();
  return (await r.json()) as Array<Record<string, unknown>>;
}

/** Accept every confirm/prompt dialog; prompts get `promptText`. */
export function acceptDialogs(page: Page, promptText = "") {
  const seen: string[] = [];
  page.on("dialog", async (d) => {
    seen.push(d.message());
    await (d.type() === "prompt" ? d.accept(promptText) : d.accept());
  });
  return seen;
}

/** With `keyFileBlocked`, the Mac app's key file goes in this folder, where a plain file stands. */
export const BLOCKED_KEY_FOLDER = "key-folder";

/**
 * The server's environment as the Mac app's launcher sets it (port, key
 * file in the test's temp dir). Use with test.use({ appMode: "mac" }).
 */
function macAppEnv(dir: string, port: number, keyFileBlocked: boolean): Record<string, string> {
  // A file where the key's folder goes: the app can't make the folder, so it can't write the key
  if (keyFileBlocked) writeFileSync(path.join(dir, BLOCKED_KEY_FOLDER), "");
  return {
    BTCTX_DESKTOP: "1",
    BTCTX_DESKTOP_PREFERRED_PORT: String(port),
    BTCTX_DESKTOP_ACTUAL_PORT: String(port),
    BTCTX_DESKTOP_URL: `http://127.0.0.1:${port}`,
    BTCTX_MCP_FILE: path.join(dir, keyFileBlocked ? BLOCKED_KEY_FOLDER : "", "mcp.json"),
  };
}

type Fixtures = {
  /** "mac": run the server as the Mac app does (see macAppEnv). */
  appMode: "server" | "mac";
  /**
   * "unset": a fresh install that hasn't chosen a price source yet.
   * "unconfirmed": public, stored by an older release with no record of the choice (asked once, #145);
   *   "unconfirmed-off" and "unconfirmed-mempool" (http://umbrel.local:3006) the same for Nobody and a Mempool.
   * "startos": set by the server, as StartOS's Price Source & Privacy action does.
   * "invalid": set by a server whose settings aren't valid (nothing is asked).
   */
  priceSource: "public" | "unset" | "unconfirmed" | "unconfirmed-off" | "unconfirmed-mempool" | "startos" | "invalid";
  /**
   * true: the prices come from a fake internet instead of stubs
   * (smoke_test.py, fake_internet), so the app's own choice of source,
   * fallback and proxy runs; outsideRequests() lists what it sent out.
   */
  fakeInternet: boolean;
  /** true: StartOS lends its Tor to the app's own choice (BTCTX_TOR_PROXY_URL, #145). */
  serverTor: boolean;
  /** true (with appMode "mac"): the key file can't be written at start, so the app has no AI key (#238). */
  keyFileBlocked: boolean;
  app: App;
  /** A page whose browser session is logged in (via the UI) on a fresh account. */
  authedPage: Page;
};

export const test = base.extend<Fixtures>({
  appMode: ["server", { option: true }],
  priceSource: ["public", { option: true }],
  fakeInternet: [false, { option: true }],
  serverTor: [false, { option: true }],
  keyFileBlocked: [false, { option: true }],
  app: async ({ appMode, priceSource, fakeInternet, serverTor, keyFileBlocked }, use, testInfo) => {
    const { app, proc, log } = await startApp((dir, port) => ({
      ...(appMode === "mac" ? macAppEnv(dir, port, keyFileBlocked) : {}),
      ...(fakeInternet ? { BTCTX_SMOKE_OUTSIDE_LOG: path.join(dir, OUTSIDE_LOG) } : {}),
      ...(priceSource === "unset" || priceSource.startsWith("unconfirmed") ? { BTCTX_SMOKE_PRICE_SOURCE: priceSource } : {}),
      ...(priceSource === "invalid" ? { BTCTX_PRICE_SOURCE: "coingecko" } : {}),
      ...(serverTor ? { BTCTX_HOST: "startos", BTCTX_TOR_PROXY_URL: "socks5h://10.0.3.1:9050" } : {}),
      ...(priceSource === "startos"
        ? {
            BTCTX_PRICE_SOURCE: "mempool", BTCTX_MEMPOOL_URL: "http://10.0.3.1:32768", BTCTX_MEMPOOL_FALLBACK: "off",
            BTCTX_HOST: "startos",
          }
        : {}),
    }));
    await use(app);
    proc.kill();
    if (testInfo.status !== testInfo.expectedStatus) {
      await testInfo.attach("server.log", { body: log.join("") });
    }
    rmSync(app.dir, { recursive: true, force: true });
  },
  baseURL: async ({ app }, use) => {
    await use(app.url);
  },
  authedPage: async ({ page, app }, use) => {
    await claimAccount(page.request, app);
    await loginViaUi(page);
    await use(page);
  },
});

export { expect };

/** The UTC instant the browser means by a local wall-clock time. */
export async function localToIso(page: Page, local: string): Promise<string> {
  return page.evaluate((l) => new Date(l).toISOString(), local);
}

/** Open Transactions → Add Transaction and pick a type. */
export async function openAddForm(page: Page, type: string) {
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("button", { name: "Add Transaction" }).click();
  await expect(page.getByRole("heading", { name: "Add Transaction" })).toBeVisible();
  await page.getByLabel("Transaction Type").selectOption(type);
}

// Settings' sections whose region tests know by another name than their title
const SECTION_REGION: Record<string, string> = {
  "Ledger Review": "Ledger review",
  "Privacy & Network": "Privacy & network",
};

/**
 * One of Settings' sections, opened by its button if it isn't, on the
 * Settings page already: its region. One is open at a time (#355), so
 * opening one closes the one before.
 */
export async function openSection(page: Page, title: string) {
  const button = page.getByRole("button", { name: title, exact: true });
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
  await expect(button).toHaveAttribute("aria-expanded", "true");
  return page.getByRole("region", { name: SECTION_REGION[title] ?? title });
}

/** Save the open form and wait for the panel to close. */
export async function saveForm(page: Page, button = "Save Transaction") {
  await page.getByRole("button", { name: button }).click();
  await expect(page.getByRole("heading", { name: /^(Add|Edit) Transaction$/ })).toHaveCount(0);
}

/** Seed a funded ledger over the API: $100k in the bank, 1 BTC bought 2023-01-10. */
export async function seedFunds(request: APIRequestContext) {
  await createTx(request, {
    type: "Deposit", timestamp: "2023-01-02T18:00:00Z", from_account_id: 99, to_account_id: 1,
    amount: "100000", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  await createTx(request, {
    type: "Buy", timestamp: "2023-01-10T18:00:00Z", from_account_id: 1, to_account_id: 4,
    amount: "1", cost_basis_usd: "20000.00", fee_amount: "0", fee_currency: "USD",
  });
}

/**
 * A labelled figure on the page (e.g. "Bank (USD): $80000.00") as a number.
 * Tolerates the formats the UI polish may bring: thousands separators, a
 * Unicode minus, a sign before the $, no trailing colon on the label.
 */
export async function figure(page: Page, label: string): Promise<number> {
  const esc = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const row = page.getByRole("paragraph").filter({ hasText: new RegExp(`^\\s*${esc}:?`) });
  await expect(row).toHaveCount(1);
  await expect(row).not.toContainText("Loading");
  const text = (await row.innerText()).replace(new RegExp(`^\\s*${esc}:?`), "");
  return parseFigure(text);
}

export function parseFigure(text: string): number {
  const m = text.replace(/[,\s]/g, "").replace(/−/g, "-").match(/([+-]?)\$?([+-]?)(\d+(?:\.\d+)?)/);
  if (!m) throw new Error(`no number in "${text}"`);
  const neg = m[1] === "-" || m[2] === "-";
  return (neg ? -1 : 1) * Number(m[3]);
}

/**
 * A known ledger with hand-computed results (see dashboard.e2e.ts):
 * $100k in, 1 BTC bought for $20k, sells short- and long-term, a transfer
 * with a BTC fee and an income deposit.
 */
export async function seedKnownLedger(request: APIRequestContext) {
  await seedFunds(request);
  const tx = (d: TxPayload) => createTx(request, d);
  await tx({ type: "Sell", timestamp: "2023-06-01T15:00:00Z", from_account_id: 4, to_account_id: 3,
    amount: "0.25", gross_proceeds_usd: "7000", fee_amount: "20", fee_currency: "USD" });
  await tx({ type: "Transfer", timestamp: "2023-07-01T15:00:00Z", from_account_id: 4, to_account_id: 2,
    amount: "0.5", fee_amount: "0.0001", fee_currency: "BTC" });
  await tx({ type: "Deposit", timestamp: "2024-02-01T15:00:00Z", from_account_id: 99, to_account_id: 2,
    amount: "0.01", source: "Income", fee_amount: "0", fee_currency: "BTC" });
  await tx({ type: "Sell", timestamp: "2024-03-01T15:00:00Z", from_account_id: 4, to_account_id: 3,
    amount: "0.1", gross_proceeds_usd: "9000", fee_amount: "0", fee_currency: "USD" });
}

/** Text of a downloaded PDF, via pypdf (already a backend dependency). */
export function pdfText(file: string): string {
  return execFileSync(python(), [path.join(__dirname, "pdf_text.py"), file], { encoding: "utf8" });
}
