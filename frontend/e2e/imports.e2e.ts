// River CSV import (preview statuses, edits, execute, re-import) and the
// generic CSV import (template, instructions, empty-database import).
import { test, expect, createTx, listTx, acceptDialogs, seedFunds, SAVE_ANYWAY } from "./fixtures";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const RIVER_HEADER =
  "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag";
// Row numbers count the header as row 1.
const RIVER_ROWS = [
  "2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy", //            row 2: matched
  "2026-01-12 12:00:00,25.00,USD,0.00031000,BTC,,,Buy", //            row 3: discrepancy (similar)
  "2026-02-03 15:30:00,148.50,USD,0.00180000,BTC,1.50,USD,Buy", //    row 4: new
  "2026-02-10 16:00:00,0.00050000,BTC,55.00,USD,0.55,USD,Sell", //    row 5: new
  "2026-02-01 09:00:00,,,0.00002000,BTC,,,Interest", //               row 6: new
  "2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,", //          row 7: new (send)
];
const RIVER_CSV = [RIVER_HEADER, ...RIVER_ROWS].join("\n") + "\n";

function river(page: Page) {
  return page.getByRole("region", { name: "Import from River" });
}

function riverRow(page: Page, n: number) {
  return river(page).getByRole("row").filter({ has: page.getByLabel(`Include row ${n}`) });
}

/**
 * Click River's Import of `count` rows. Once these rows' year is a past tax
 * year (from 1 January after they were written), the import asks first
 * (2.0 spec 5.8, #353): its dialog is confirmed, so the test doesn't change
 * on its own each year.
 */
async function importRiver(page: Page, count: number) {
  await river(page).getByRole("button", { name: `Import ${count} Transaction(s)` }).click();
  const saveAnyway = page.getByRole("button", { name: SAVE_ANYWAY });
  const imported = page.getByText(new RegExp(`Imported ${count} transaction`, "i"));
  await expect.poll(async () => (await saveAnyway.isVisible()) || (await imported.isVisible())).toBe(true);
  if (await saveAnyway.isVisible()) await saveAnyway.click();
}

async function previewRiver(page: Page) {
  await page.getByRole("link", { name: "Settings" }).click();
  const r = river(page);
  await r.getByLabel("River CSV file").setInputFiles({
    name: "river.csv", mimeType: "text/csv", buffer: Buffer.from(RIVER_CSV),
  });
  await r.getByRole("button", { name: "Preview" }).click();
  await expect(r.getByText("6 rows in file")).toBeVisible();
}

test("River import: preview statuses, edits, execute, re-import; a ticked duplicate is imported (#253)", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  const tx = (d: Record<string, string | number>) => createTx(page.request, {
    type: "Buy", from_account_id: 1, to_account_id: 4, fee_amount: "0", fee_currency: "USD", ...d,
  });
  // The same kind, amount and minute as row 2 (another basis: River compares
  // nothing else, #253); row 3's amount 3 hours later: only similar
  await tx({ timestamp: "2026-01-05T12:00:00Z", amount: "0.00030000", cost_basis_usd: "10.00" });
  await tx({ timestamp: "2026-01-12T15:00:00Z", amount: "0.00031000", cost_basis_usd: "25.00" });
  const before = (await listTx(page.request)).length;

  await previewRiver(page);
  const r = river(page);
  await expect(r.getByText("4 new")).toBeVisible();
  await expect(r.getByText("1 already in ledger")).toBeVisible();
  await expect(r.getByText("1 need review")).toBeVisible();
  await expect(r.getByText(/Row 3: Same BTC amount as tx #\d+ \(Buy 0\.00031000 BTC\), recorded 3 hours later/)).toBeVisible();

  // Matched rows are hidden until asked for, and start unticked (#253).
  await expect(r.getByLabel("Include row 2")).toHaveCount(0);
  await r.getByRole("button", { name: "Show 1 already-imported row(s)" }).click();
  await expect(r.getByLabel("Include row 2")).toBeEnabled();
  await expect(r.getByLabel("Include row 2")).not.toBeChecked();
  await expect(riverRow(page, 2)).toContainText("In ledger");
  await expect(r.getByText(/Tick one to import it anyway/)).toBeVisible();
  await r.getByRole("button", { name: "Hide already-imported rows" }).click();

  // A row to review starts ticked, as new rows do: never left out by itself (#253).
  await expect(r.getByLabel("Include row 3")).toBeChecked();
  await expect(riverRow(page, 3)).toContainText("Review");
  for (const n of [4, 5, 6, 7]) await expect(r.getByLabel(`Include row ${n}`)).toBeChecked();
  await expect(riverRow(page, 4)).toContainText("New");
  // Each fee with its unit, and a tagged payout's source under its type (#269)
  await expect(riverRow(page, 4)).toContainText("$1.50");
  await expect(riverRow(page, 5)).toContainText("$0.55");
  await expect(riverRow(page, 6).getByText("Interest", { exact: true })).toBeVisible();

  // Edits: the interest payout's basis, the send's fee; leave out the sell,
  // and row 3, the buy already recorded.
  await riverRow(page, 6).getByLabel("Cost basis (USD)").fill("2.10");
  await riverRow(page, 7).getByLabel("Fee (BTC)").fill("0.00000600");
  await r.getByLabel("Include row 5").uncheck();
  await r.getByLabel("Include row 3").uncheck();

  const dialogs = acceptDialogs(page);
  await importRiver(page, 3);
  await expect(page.getByText(/Imported 3/i)).toBeVisible();
  expect(dialogs).toEqual(["Import 3 transaction(s) from River into your ledger?"]);

  const all = await listTx(page.request);
  expect(all).toHaveLength(before + 3);
  const interest = all.find((t) => t.source === "Interest")!;
  expect(Number(interest.cost_basis_usd)).toBe(2.1);
  const send = all.find((t) => t.type === "Transfer")!;
  expect(Number(send.fee_amount)).toBe(0.000006);
  const buy = all.find((t) => t.type === "Buy" && Number(t.amount) === 0.0018)!;
  expect(Number(buy.cost_basis_usd)).toBe(148.5);
  expect(Number(buy.fee_amount)).toBe(1.5);
  expect(all.find((t) => t.type === "Sell")).toBeUndefined();

  // Re-import: what was imported is matched, the send whose fee was edited
  // too (River's own amount, #253); row 3 still needs review; the sell is new.
  await previewRiver(page);
  await expect(r.getByText("4 already in ledger")).toBeVisible();
  await expect(r.getByText("1 need review")).toBeVisible();
  await expect(r.getByText("1 new")).toBeVisible();
  await expect(riverRow(page, 5)).toContainText("New");

  // A row already in the ledger, ticked, is imported all the same, and stays
  // in sight when the others are hidden (#253).
  await r.getByRole("button", { name: "Show 4 already-imported row(s)" }).click();
  await expect(riverRow(page, 7)).toContainText("In ledger");
  await r.getByLabel("Include row 2").check();
  await r.getByRole("button", { name: "Hide already-imported rows" }).click();
  await expect(r.getByLabel("Include row 2")).toBeChecked();
  await expect(r.getByLabel("Include row 4")).toHaveCount(0);
  for (const n of [3, 5]) await r.getByLabel(`Include row ${n}`).uncheck();
  await importRiver(page, 1);
  await expect(page.getByText(/Imported 1/i)).toBeVisible();
  const after = await listTx(page.request);
  expect(after).toHaveLength(before + 4);
  expect(after.filter((t) => t.type === "Buy" && Number(t.amount) === 0.0003)).toHaveLength(2);
});

test("River import rejects a file that isn't a River export", async ({ authedPage: page }) => {
  await page.getByRole("link", { name: "Settings" }).click();
  const r = river(page);
  await r.getByLabel("River CSV file").setInputFiles({
    name: "other.csv", mimeType: "text/csv", buffer: Buffer.from("date,type,amount\n2026-01-01,Buy,1\n"),
  });
  await r.getByRole("button", { name: "Preview" }).click();
  await expect(r.getByText(/This does not look like a River bitcoin-activity CSV\. Missing columns:/)).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(0);
});

test("River preview: every column fits a 1440-wide window, the page widens only while it's open (#259)", async ({ authedPage: page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const settingsWidth = () => page.locator(".settings-page").evaluate((e) => e.clientWidth);
  await page.getByRole("link", { name: "Settings" }).click();
  const narrow = await settingsWidth();
  await previewRiver(page);
  await expect.poll(settingsWidth).toBeGreaterThan(narrow);
  const table = river(page).locator(".river-table");
  const fit = await table.evaluate((t) => ({ table: t.scrollWidth, room: t.closest(".table-scroll")!.clientWidth }));
  expect(fit.table).toBeLessThanOrEqual(fit.room);

  await river(page).getByRole("button", { name: "Cancel" }).click();
  await expect(table).toHaveCount(0);
  await expect.poll(settingsWidth).toBe(narrow);
});

function data(page: Page) {
  return page.getByRole("region", { name: "Data Management" });
}

async function download(page: Page, button: string) {
  const d = page.waitForEvent("download");
  await data(page).getByRole("button", { name: button }).click();
  const got = await d;
  return { name: got.suggestedFilename(), file: (await got.path())! };
}

test("CSV import: template and instructions download; the template imports into an empty ledger", async ({ authedPage: page }) => {
  await page.getByRole("link", { name: "Settings" }).click();
  const tpl = await download(page, "Template");
  expect(tpl.name).toBe("btctx_import_template.csv");
  const template = readFileSync(tpl.file, "utf8");
  expect(template.split(/\r?\n/)[0]).toMatch(/date/i);

  const ins = await download(page, "Instructions");
  expect(readFileSync(ins.file).subarray(0, 4).toString()).toBe("%PDF");

  await data(page).getByLabel("CSV file to import").setInputFiles({
    name: "import.csv", mimeType: "text/csv", buffer: Buffer.from(template),
  });
  await data(page).getByRole("button", { name: "Preview" }).click();
  await expect(data(page).getByRole("heading", { name: "Import Preview" })).toBeVisible();
  // Dollars as dollars, bitcoin as bitcoin, the accounts by their usual names (#254)
  const rows = data(page).getByRole("row");
  await expect(rows.nth(1)).toContainText("$20,000.00");
  await expect(rows.nth(1)).not.toContainText("BTC");
  await expect(rows.nth(2)).toContainText(/Bank\s*Exchange USD/);
  await expect(rows.nth(3)).toContainText("0.50000000 BTC");
  const stats = await data(page).getByText(/valid \/ \d+ total rows/).innerText();
  const valid = Number(stats.match(/(\d+) valid/)![1]);
  expect(valid).toBeGreaterThan(0);

  acceptDialogs(page);
  await data(page).getByRole("button", { name: `Import ${valid} Transactions` }).click();
  await expect.poll(async () => (await listTx(page.request)).length).toBe(valid);
});

test("CSV import refuses a ledger that already has transactions", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  await page.getByRole("link", { name: "Settings" }).click();
  const tpl = await download(page, "Template");
  await data(page).getByLabel("CSV file to import").setInputFiles({
    name: "import.csv", mimeType: "text/csv", buffer: readFileSync(tpl.file),
  });
  await data(page).getByRole("button", { name: "Preview" }).click();
  await expect(page.getByText(/Database has 2 existing transaction\(s\)/)).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(2);
});
