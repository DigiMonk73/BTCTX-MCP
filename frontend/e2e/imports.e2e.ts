// River CSV import (preview statuses, edits, execute, re-import) and the
// generic CSV import (template, instructions, empty-database import).
import { test, expect, createTx, listTx, acceptDialogs, seedFunds } from "./fixtures";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const RIVER_HEADER =
  "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag";
// Row numbers count the header as row 1.
const RIVER_ROWS = [
  "2026-01-05 12:00:00,25.00,USD,0.00030000,BTC,,,Buy", //            row 2: matched
  "2026-01-12 12:00:00,25.00,USD,0.00031000,BTC,,,Buy", //            row 3: discrepancy
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

async function previewRiver(page: Page) {
  await page.getByRole("link", { name: "Settings" }).click();
  const r = river(page);
  await r.getByLabel("River CSV file").setInputFiles({
    name: "river.csv", mimeType: "text/csv", buffer: Buffer.from(RIVER_CSV),
  });
  await r.getByRole("button", { name: "Preview" }).click();
  await expect(r.getByText("6 rows in file")).toBeVisible();
}

test("River import: preview statuses, edits, execute, re-import skips", async ({ authedPage: page }) => {
  await seedFunds(page.request);
  const tx = (d: Record<string, string | number>) => createTx(page.request, {
    type: "Buy", from_account_id: 1, to_account_id: 4, fee_amount: "0", fee_currency: "USD", ...d,
  });
  await tx({ timestamp: "2026-01-05T15:00:00Z", amount: "0.00030000", cost_basis_usd: "25.00" });
  await tx({ timestamp: "2026-01-12T15:00:00Z", amount: "0.00031000", cost_basis_usd: "10.00" });
  const before = (await listTx(page.request)).length;

  await previewRiver(page);
  const r = river(page);
  await expect(r.getByText("4 new")).toBeVisible();
  await expect(r.getByText("1 already in ledger")).toBeVisible();
  await expect(r.getByText("1 need review")).toBeVisible();
  await expect(r.getByText(/Row 3: .*differs/)).toBeVisible();

  // Matched rows are hidden until asked for, and can't be ticked.
  await expect(r.getByLabel("Include row 2")).toHaveCount(0);
  await r.getByRole("button", { name: "Show 1 already-imported row(s)" }).click();
  await expect(r.getByLabel("Include row 2")).toBeDisabled();
  await expect(riverRow(page, 2)).toContainText("In ledger");
  await r.getByRole("button", { name: "Hide already-imported rows" }).click();

  // Discrepancies start unticked; new rows start ticked.
  await expect(r.getByLabel("Include row 3")).not.toBeChecked();
  await expect(riverRow(page, 3)).toContainText("Review");
  for (const n of [4, 5, 6, 7]) await expect(r.getByLabel(`Include row ${n}`)).toBeChecked();
  await expect(riverRow(page, 4)).toContainText("New");

  // Edits: the interest payout's basis, the send's fee; leave out the sell.
  await riverRow(page, 6).getByLabel("Cost basis (USD)").fill("2.10");
  await riverRow(page, 7).getByLabel("Fee (BTC)").fill("0.00000600");
  await r.getByLabel("Include row 5").uncheck();

  const dialogs = acceptDialogs(page);
  await r.getByRole("button", { name: "Import 3 Transaction(s)" }).click();
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

  // Re-import: what was imported as River had it is matched; the send whose
  // fee was edited differs from River, so it needs review; the sell is new.
  await previewRiver(page);
  await expect(r.getByText("3 already in ledger")).toBeVisible();
  await expect(r.getByText("2 need review")).toBeVisible();
  await expect(r.getByText("1 new")).toBeVisible();
  await expect(riverRow(page, 7)).toContainText("Review");
  await expect(riverRow(page, 5)).toContainText("New");
  await r.getByRole("button", { name: "Cancel" }).click();
  await expect(r.getByText("rows in file")).toHaveCount(0);
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
