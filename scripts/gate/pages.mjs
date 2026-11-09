#!/usr/bin/env node
// The release gate's sign-in and password pages in a browser (#935, for #924):
// docs/AGENT-TESTS.md's AUTH-1 to AUTH-3, BAK-2, BAK-3, SEC-8 and END-2, each
// PASS or FAIL with what it saw, in OUT_DIR/results.json and a screenshot of
// each FAIL. scripts/gate/pages.py runs it against the candidate's own image
// and gives it:
//   GATE_PASSWORD   admin's password, as Set Login Credentials made it (INS-3)
//   GATE_CONTAINER  the candidate's container, for its data folder (END-2)
//   GATE_PY         a Python with the gate's scripts' needs (pypdf)
//
//     node scripts/gate/pages.mjs URL OUT_DIR
//
// Test logins only, typed only into a page on this computer: any other host
// is refused before anything else runs. A step that fails doesn't stop the
// run (AGENT-TESTS.md's rule 3); a later step that needed it fails too.
import { execFileSync, spawnSync } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import { fileURLToPath } from "node:url";

const THIS_COMPUTER = ["127.0.0.1", "localhost"];

/** The URL's origin, if it's on this computer; else exit 2. The origin, not the
 * text given, so every request goes where the check looked. */
function localUrl(raw) {
  let url;
  try {
    url = new URL(raw);
  } catch {
    url = null;
  }
  if (!url || !["http:", "https:"].includes(url.protocol) || !THIS_COMPUTER.includes(url.hostname)
      || url.username || url.password) {
    console.error(`refused: ${raw}: test logins go only to a page on this computer, ${THIS_COMPUTER.join(" or ")}`);
    process.exit(2);
  }
  return url.origin;
}

const BASE = localUrl(process.argv[2] ?? "");
const OUT = process.argv[3] ?? ".";
const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
// The frontend's own Playwright: the gate adds no package of its own
const { chromium, request } = createRequire(path.join(REPO, "frontend", "package.json"))("@playwright/test");

const ADMIN = process.env.GATE_PASSWORD;
const CONTAINER = process.env.GATE_CONTAINER;
const PY = process.env.GATE_PY ?? "python3";
// The guide's own test values (AGENT-TESTS.md: BAK-2, SEC-8, END-2)
const BACKUP_PASSWORD = "backup-pass-123";
const TESTER = ["tester", "tester-password-1"];
const FRESH = ["fresh", "fresh-password-12"];
const WAIT = 15_000;
const HIDDEN = "<the test login>";

class Fail extends Error {}

/** Evidence without admin's random password: Playwright's errors quote what
 * a fill typed, and the evidence goes into the gate's report. */
function scrubbed(text) {
  return ADMIN ? String(text).replaceAll(ADMIN, HIDDEN) : String(text);
}
const results = [];
const dialogs = [];

mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch();
// AUTH-3: a login adopts the browser's timezone while the ledger is empty
const context = await browser.newContext({ baseURL: BASE, timezoneId: "America/New_York", locale: "en-US" });
const page = await context.newPage();
page.setDefaultTimeout(WAIT);
page.on("dialog", (dialog) => {
  dialogs.push(dialog.message());
  void dialog.accept();
});

/** One step: PASS with what it saw, or FAIL with what it saw and a screenshot. */
async function step(id, title, body) {
  const saw = [];
  let verdict = "PASS";
  try {
    await body(saw);
  } catch (error) {
    verdict = "FAIL";
    saw.push(scrubbed(error instanceof Fail ? error.message : `error: ${error.message ?? error}`));
    await page.screenshot({ path: path.join(OUT, `${id}.png`), fullPage: true }).catch(() => {});
  }
  results.push({ id, title, verdict, saw });
  console.log(`${verdict} ${id} ${title}: ${saw.join("; ")}`);
}

function check(ok, what) {
  if (!ok) throw new Fail(what);
}

/** The page's own text, short, for a FAIL's evidence. */
async function shown(where = page.locator("body")) {
  return (await where.innerText().catch(() => "")).replace(/\s+/g, " ").trim().slice(0, 400);
}

/** `text` appears in `where`; noted as seen. Settings says what a form did
 * in its message line, below the sections: look for that in the page. */
async function sees(where, text, saw, timeout = WAIT) {
  try {
    await where.getByText(text).first().waitFor({ state: "visible", timeout });
  } catch {
    throw new Fail(`expected "${text}"; the page shows: ${await shown()}`);
  }
  saw.push(`"${text}"`);
}

async function at(pattern, what, timeout = WAIT) {
  try {
    await page.waitForURL(pattern, { timeout });
  } catch {
    throw new Fail(`expected ${what}; at ${page.url()}: ${await shown()}`);
  }
}

async function logIn(user, password, where = page) {
  await where.goto("/login");
  await where.getByLabel("Username").fill(user);
  await where.getByLabel("Password", { exact: true }).fill(password);
  await where.getByRole("button", { name: "Log in" }).click();
}

/** The header's Logout (a link), confirmed. */
async function logOut(saw) {
  await page.getByRole("link", { name: "Logout", exact: true }).click();
  await at(/\/login$/, "the login page after Logout");
  saw.push("logged out");
}

/** One of Settings' sections, opened: its region. Settings is loaded again,
 * since a page left open keeps what it read then, not what the steps'
 * setup (the API) changed since. */
async function settings(title) {
  await page.goto("/settings");
  const button = page.getByRole("button", { name: title, exact: true });
  if ((await button.getAttribute("aria-expanded")) !== "true") await button.click();
  return page.getByRole("region", { name: title });
}

async function api(method, route, data) {
  const answer = await page.request.fetch(route, { method, data });
  if (!answer.ok()) throw new Fail(`${method} ${route}: ${answer.status()} ${(await answer.text()).slice(0, 200)}`);
  return answer.status() === 204 ? null : answer.json();
}

async function rows() {
  return (await api("GET", "/api/transactions")).length;
}

/** One of the gate's Python scripts against this install, logged in as `login`:
 * its exit code and what it printed. */
function gatePython(script, args, [user, password]) {
  const run = spawnSync(PY, [path.join(REPO, "scripts", "gate", script), ...args], {
    env: { ...process.env, BTCTX_URL: BASE, BTCTX_USER: user, BTCTX_PASSWORD: password },
    encoding: "utf8",
  });
  return { code: run.status, out: scrubbed(`${run.stdout ?? ""}${run.stderr ?? ""}${run.error ?? ""}`.trim()) };
}

/** The same, failing the step when it fails. */
function gateScript(script, args, login) {
  const run = gatePython(script, args, login);
  if (run.code !== 0) throw new Fail(`${script} ${args[0] ?? ""} failed: ${run.out.slice(-400)}`);
  return run.out;
}

/** The safety copies a Delete All or a reset leaves in the data folder (IMP-3, END-2). */
function deleteAllCopies() {
  const listed = execFileSync("docker", ["exec", CONTAINER, "ls", "/data/backups"], { encoding: "utf8" });
  return listed.split("\n").filter((name) => /^btctx-before-delete-all-.*\.db$/.test(name));
}

/** What a request with the AI key gets: its status. */
async function withKey(key) {
  const ai = await request.newContext({ baseURL: BASE });
  const answer = await ai.get("/api/transactions", { headers: { Authorization: `Bearer ${key}` } });
  await ai.dispose();
  return answer.status();
}

let backupFile = null;
let olderKey = null;

await step("AUTH-1", "the sign-in page", async (saw) => {
  // The Setup Code field shows only once the server has said it's needed
  const status = page.waitForResponse((answer) => answer.url().endsWith("/api/users/setup-status"));
  await page.goto("/");
  await status;
  await sees(page, "Welcome to BitcoinTX", saw);
  await sees(page, "Sign in", saw);
  check((await page.getByLabel("Setup Code").count()) === 0, "a Setup Code field is shown");
  saw.push("no Setup Code field");
  const password = page.getByLabel("Password", { exact: true });
  await password.fill("typed-to-show");
  check((await password.getAttribute("type")) === "password", "the password shows as it's typed");
  await page.getByRole("button", { name: "Show password" }).click();
  check((await password.getAttribute("type")) === "text" && (await password.inputValue()) === "typed-to-show",
    "Show password doesn't show the typed password");
  saw.push("Show password shows the typed password");
});

await step("AUTH-2", "a wrong password, and the default login", async (saw) => {
  for (const [user, password] of [["admin", "a-wrong-password"], ["admin", "password"]]) {
    await logIn(user, password);
    await sees(page.getByRole("alert"), "Invalid username or password.", saw);
    check(page.url().endsWith("/login"), `${user} / ${password === "password" ? "password" : "a wrong one"} got in`);
  }
});

await step("AUTH-3", "the INS-3 login, and the timezone it adopts", async (saw) => {
  await logIn("admin", ADMIN);
  await at(/\/dashboard$/, "the Dashboard");
  saw.push("the Dashboard");
  await sees(await settings("Account"), "Current: America/New_York", saw);
});

// What BAK-3 and END-2 count on, as the gate's earlier steps leave it: the
// golden ledger (GLD), Coldcard and Kraken (ACC, MLT), and an AI key (AI)
try {
  const loaded = gateScript("golden_loader.py", [], ["admin", ADMIN]);
  await api("POST", "/api/accounts/", { kind: "wallet", name: "Coldcard" });
  await api("POST", "/api/accounts/", { kind: "exchange", name: "Kraken", sends_1099da: true });
  await api("PUT", "/api/settings/ai-access", { on: true });
  olderKey = (await api("POST", "/api/settings/ai-key")).key;
  gateScript("figures.py", ["snap", path.join(OUT, "before-backup.json")], ["admin", ADMIN]);
  console.log(`ready for BAK: ${loaded}; Coldcard and Kraken added; AI access on, with a key`);
} catch (error) {
  console.log(`not ready for BAK: ${scrubbed(error.message)}`);
}

await step("BAK-2", "the encrypted backup's password", async (saw) => {
  const section = await settings("Backup & Restore");
  const first = section.getByLabel("Encrypt with password");
  const repeat = section.getByLabel("Repeat password");
  check((await first.getAttribute("type")) === "password" && (await repeat.getAttribute("type")) === "password",
    "a backup password shows as it's typed");
  saw.push("both boxes hidden as typed");
  let downloads = 0;
  const counted = () => downloads++;
  page.on("download", counted);
  for (const [one, two, refusal] of [
    [BACKUP_PASSWORD, "backup-pass-124", "The two passwords don't match."],
    ["backup-pass", "backup-pass", "The password is too short. At least 12 characters."],
  ]) {
    await first.fill(one);
    await repeat.fill(two);
    await section.getByRole("button", { name: "Download" }).click();
    await sees(page, refusal, saw);
  }
  page.off("download", counted);
  check(downloads === 0, `a refused password downloaded ${downloads} file(s)`);
  saw.push("nothing downloaded");
  await first.fill(BACKUP_PASSWORD);
  await repeat.fill(BACKUP_PASSWORD);
  // Waited for with the click: a wait begun earlier would outlive a fill that failed
  const [file] = await Promise.all([
    page.waitForEvent("download"), section.getByRole("button", { name: "Download" }).click(),
  ]);
  check(file.suggestedFilename() === "bitcoin_backup.btx", `the file is ${file.suggestedFilename()}`);
  backupFile = path.join(OUT, "bitcoin_backup.btx");
  await file.saveAs(backupFile);
  saw.push("bitcoin_backup.btx");
  await sees(page, "Backup downloaded.", saw);
});

await step("BAK-3", "the restore: a wrong password, then the right one", async (saw) => {
  check(backupFile, "no backup from BAK-2");
  // A row the backup doesn't have: the restore must take it away
  await api("POST", "/api/transactions", {
    type: "Deposit", timestamp: "2026-01-02T17:00:00Z", from_account_id: 99, to_account_id: 1,
    amount: "1", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  const before = await rows();
  const ai = await settings("Connect an AI Assistant");
  await ai.getByRole("button", { name: "New key" }).click();
  const shownKey = page.getByRole("group", { name: "New AI key" }).locator("textarea, input, code, pre").first();
  await shownKey.waitFor({ timeout: WAIT });
  const key = ((await shownKey.inputValue().catch(() => null)) ?? (await shownKey.innerText())).trim();
  check(key.length > 20, "no new AI key shown");
  saw.push("a new AI key");

  const section = await settings("Backup & Restore");
  await section.getByLabel("Backup file").setInputFiles(backupFile);
  await section.getByLabel("Backup password").fill("wrong-pass");
  await section.getByRole("button", { name: "Restore", exact: true }).click();
  await sees(page, "Restore failed: ❌ Failed to decrypt backup. Wrong password, or the file is damaged or isn't a BitcoinTX backup.", saw);
  check((await rows()) === before, "a refused restore changed the ledger");
  saw.push(`the ledger unchanged (${before} rows)`);

  await section.getByLabel("Backup file").setInputFiles(backupFile);
  await section.getByLabel("Backup password").fill(BACKUP_PASSWORD);
  await section.getByRole("button", { name: "Restore", exact: true }).click();
  await sees(page, "✅ Database successfully restored. Log in again with your current username and password.", saw, 60_000);
  // #943: a notice waits on screen until it's read, then the button leaves
  const again = page.getByRole("button", { name: "Log in again" });
  if (await again.isVisible()) {
    saw.push(`a notice held the page: "${await shown(page.getByRole("status"))}"`);
    await again.click();
  }
  await at(/\/login$/, "the login page after the restore");
  saw.push("the login page");

  await logIn("admin", ADMIN);
  await at(/\/dashboard$/, "the Dashboard with the login in use before the restore");
  saw.push("the login in use before the restore logs in");
  gateScript("figures.py", ["snap", path.join(OUT, "after-restore.json")], ["admin", ADMIN]);
  const compared = gatePython("figures.py",
    ["compare", path.join(OUT, "before-backup.json"), path.join(OUT, "after-restore.json")], ["admin", ADMIN]);
  writeFileSync(path.join(OUT, "BAK-3-figures.txt"), compared.out + "\n");
  const last = compared.out.split("\n").at(-1);
  check(compared.code === 0, `the figures differ from the backup's (BAK-3-figures.txt): ${last}`);
  saw.push(`every golden figure as backed up (${last})`);
  const names = (await api("GET", "/api/accounts/")).map((a) => a.name);
  check(names.includes("Coldcard") && names.includes("Kraken BTC"), `the accounts are ${names.join(", ")}`);
  saw.push("Coldcard and Kraken");
  const [newer, older] = [await withKey(key), await withKey(olderKey)];
  check(newer === 200, `the key made before the restore answers ${newer}`);
  check(older === 401, `the backup's older key answers ${older}`);
  saw.push("the key made before the restore works (200), the backup's older one doesn't (401)");
});

await step("SEC-8", "the password rules, and another browser's session", async (saw) => {
  const other = await browser.newContext({ baseURL: BASE, timezoneId: "America/New_York" });
  const second = await other.newPage();
  await logIn("admin", ADMIN, second);
  await second.waitForURL(/\/dashboard$/, { timeout: WAIT });
  saw.push("a second browser logged in");

  const account = await settings("Account");
  const submit = () => account.getByRole("button", { name: "Update" }).click();
  await account.getByLabel("New username").fill(TESTER[0]);
  await account.getByLabel("New password").fill("elevenchars");
  await account.getByLabel("Current password").fill(ADMIN);
  await submit();
  await sees(page, "The new password is too short. At least 12 characters.", saw);
  await account.getByLabel("New password").fill(TESTER[1]);
  await account.getByLabel("Current password").fill("");
  await submit();
  await sees(page, "Enter your current password to change your username or password.", saw);
  await account.getByLabel("Current password").fill(ADMIN);
  await submit();
  await sees(page, "Credentials updated successfully.", saw);

  // #943: the other browser's next click goes to the sign-in page
  await second.getByRole("link", { name: "Transactions" }).click();
  try {
    await second.waitForURL(/\/login$/, { timeout: WAIT });
  } catch {
    throw new Fail(`the second browser stayed at ${second.url()}: ${await shown(second.locator("body"))}`);
  }
  saw.push("the second browser's next click lands on the login page");
  await other.close();

  await logOut(saw);
  await logIn(...TESTER);
  await at(/\/dashboard$/, "the Dashboard as tester");
  saw.push("tester logs in");
});

await step("END-2", "the reset from the register page", async (saw) => {
  const copies = deleteAllCopies().length;
  await logOut(saw);
  await page.goto("/register");
  const current = page.getByLabel("Current Password");
  await current.waitFor({ timeout: WAIT }).catch(() => {});
  check((await current.count()) === 1, `no Current Password field: ${await shown()}`);
  check((await page.getByLabel("Setup Code").count()) === 0, "a Setup Code field is shown");
  saw.push("a Current Password field, no Setup Code");

  const asked = dialogs.length; // the browser's own confirm counts too (#256)
  await page.getByLabel("New Username").fill(FRESH[0]);
  await page.getByLabel("New Password").fill(FRESH[1]);
  await current.fill("not-the-current-password");
  await page.getByRole("button", { name: "Register" }).click();
  const refusal = page.getByRole("alert");
  await refusal.first().waitFor({ timeout: WAIT }).catch(() => {});
  check((await refusal.count()) > 0, `a wrong current password wasn't refused: ${await shown()}`);
  check((await page.getByRole("dialog").count()) === 0 && dialogs.length === asked,
    "a dialog came with a wrong current password");
  saw.push(`a wrong current password refused, no dialog ("${await shown(refusal.first())}")`);

  await current.fill(TESTER[1]);
  await page.getByRole("button", { name: "Register" }).click();
  const dialog = page.getByRole("dialog", { name: "Create a new account and delete every transaction?" });
  await sees(dialog, "This deletes 14 transactions, 2023–2025", saw);
  await sees(dialog, "data folder", saw);
  check(await dialog.getByRole("link", { name: "Log in" }).isVisible(), "no Log in link in the dialog");
  check((await dialog.getByRole("button", { name: /Download/ }).count()) === 0, "a download button, while logged out");
  saw.push("a Log in link, no download button");
  const go = dialog.getByRole("button", { name: "Delete 14 transactions" });
  check(await go.isDisabled(), "Delete 14 transactions is enabled before DELETE is typed");
  await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
  check(await go.isEnabled(), "Delete 14 transactions stays disabled with DELETE typed");
  saw.push("Delete 14 transactions enabled only once DELETE is typed");
  await go.click();
  await at(/\/login$/, "the login page after the reset");
  await sees(page, "Registration successful! Your credentials have been updated. A copy of the database from before "
    + "is kept in BitcoinTX's data folder (in backups, unencrypted).", saw);
  check(dialogs.length === asked, `the browser's own confirm came: ${dialogs.slice(asked).join(" / ")}`);
  saw.push("no browser confirm");
  const now = deleteAllCopies().length;
  check(now === copies + 1, `the data folder's backups went from ${copies} to ${now} copies`);
  saw.push(`one more btctx-before-delete-all-….db (${copies} → ${now})`);

  await logIn(...FRESH);
  await at(/\/dashboard$/, "the Dashboard as fresh");
  check((await rows()) === 0, "fresh's ledger isn't empty");
  saw.push("fresh logs in to an empty ledger");
  const section = await settings("Wallets, exchanges and banks");
  for (const name of ["Coldcard", "Kraken", "Bank"]) {
    const row = section.getByRole("button", { name: new RegExp(`^${name}\\b`) }).first();
    await row.click();
    const details = section.getByRole("region", { name });
    const remove = await details.getByRole("button", { name: "Delete" }).count();
    if (name === "Bank") {
      check(remove === 0, "Bank's row offers Delete");
      await sees(details, "Your first bank, wallet and exchange can't be deleted. Hide one you don't use.", saw);
    } else {
      check(remove === 1, `${name}'s row offers no Delete: ${await shown(details)}`);
      saw.push(`${name} with Delete`);
    }
    await row.click();
  }
});

await browser.close();
writeFileSync(path.join(OUT, "results.json"), JSON.stringify(results, null, 2) + "\n");
writeFileSync(path.join(OUT, "dialogs.json"), JSON.stringify(dialogs, null, 2) + "\n");
process.exit(results.every((r) => r.verdict === "PASS") ? 0 : 1);
