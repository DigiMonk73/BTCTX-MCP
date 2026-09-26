// Shared fixtures: every test gets its own backend on a fresh temp database
// (scripts/smoke_test.py --serve: historical BTC price $50,000, current
// $60,000, block height 900,000), so tests never depend on each other.
import { test as base, expect, type Page, type APIRequestContext } from "@playwright/test";
import { spawn, type ChildProcess } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
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

async function startApp(): Promise<{ app: App; proc: ChildProcess; log: string[] }> {
  const dir = mkdtempSync(path.join(os.tmpdir(), "btctx-e2e-"));
  const port = await freePort();
  const log: string[] = [];
  const proc = spawn(
    python(),
    ["scripts/smoke_test.py", "--serve", String(port), path.join(dir, "e2e.db")],
    { cwd: REPO, env: { ...process.env, PYTHONUNBUFFERED: "1" } },
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

/** Claim the default account over the API (the UI flow has its own test). */
export async function claimAccount(request: APIRequestContext) {
  const r = await request.post("/api/users/reset-account", {
    data: { username: USER, password: PASSWORD },
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

export type TxPayload = Record<string, string | number | null>;

/** Create a transaction over the API; returns the saved record. */
export async function createTx(request: APIRequestContext, data: TxPayload) {
  const r = await request.post("/api/transactions", { data });
  expect(r.ok(), await r.text()).toBeTruthy();
  return r.json();
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

type Fixtures = {
  app: App;
  /** A page whose browser session is logged in (via the UI) on a fresh account. */
  authedPage: Page;
};

export const test = base.extend<Fixtures>({
  // eslint-disable-next-line no-empty-pattern
  app: async ({}, use, testInfo) => {
    const { app, proc, log } = await startApp();
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
  authedPage: async ({ page }, use) => {
    await claimAccount(page.request);
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
