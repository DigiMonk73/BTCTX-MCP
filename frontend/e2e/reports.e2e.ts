// Reports: each export downloads the right file with the right figures.
import { test, expect, seedKnownLedger, pdfText } from "./fixtures";
import type { Page } from "@playwright/test";
import { readFileSync, writeFileSync } from "node:fs";

async function exportReport(page: Page, report: string, year: string) {
  await page.getByRole("link", { name: "Reports" }).click();
  await page.getByLabel("Tax Year").fill(year);
  await page.getByLabel(report).check();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export" }).click();
  const d = await download;
  return { name: d.suggestedFilename(), file: (await d.path())! };
}

test("export needs a year", async ({ authedPage: page }) => {
  await page.getByRole("link", { name: "Reports" }).click();
  await page.getByRole("button", { name: "Export" }).click();
  await expect(page.getByText("Please enter a valid year (e.g. 2024).")).toBeVisible();
});

test("complete tax report PDF", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  const { name, file } = await exportReport(page, "Complete Tax Report", "2024");
  expect(name).toBe("CompleteTaxReport_2024.pdf");
  expect(readFileSync(file).subarray(0, 4).toString()).toBe("%PDF");
  const text = pdfText(file);
  if (process.env.E2E_DUMP) writeFileSync(`${process.env.E2E_DUMP}/${name}.txt`, text);
  test.info().attach("text", { body: text });
  expect(text).toContain("2024");
  // Long-term sale: proceeds, basis, gain.
  expect(text).toMatch(/\$9,000\.00[\s\S]*\$2,000\.00[\s\S]*\$7,000\.00/);
  expect(text).toMatch(/\$500\.00/); // income
  expect(text).toMatch(/\$13,498\.00/); // basis still held at year end
  expect(text).toMatch(/\$20,454\.61 per BTC/);
});

test("IRS Form 8949 / Schedule D PDF", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  const { name, file } = await exportReport(page, "IRS Reports (Form 8949, Schedule D, etc.)", "2024");
  expect(name).toBe("IRSReports(Form8949,ScheduleD,etc.)_2024.pdf");
  expect(readFileSync(file).subarray(0, 4).toString()).toBe("%PDF");
  const text = pdfText(file);
  if (process.env.E2E_DUMP) writeFileSync(`${process.env.E2E_DUMP}/${name}.txt`, text);
  test.info().attach("text", { body: text });
  // Form 8949 Part II row for the long-term sale: description, acquired,
  // sold, proceeds, basis, gain; then the same totals on Schedule D.
  const row = /0\.10000000 BTC\s+01\/10\/2023\s+03\/01\/2024\s+9,?000\.00\s+2,?000\.00\s+7,?000\.00/g;
  expect(text.match(row)).toHaveLength(1);
  expect(text.match(/9,?000\.00\s+2,?000\.00\s+7,?000\.00/g)!.length).toBeGreaterThanOrEqual(2);
  // No short-term sales in 2024.
  expect(text).not.toMatch(/0\.25000000 BTC/);
});

test("transaction history CSV", async ({ authedPage: page }) => {
  await seedKnownLedger(page.request);
  const { name, file } = await exportReport(page, "Transaction History", "2023");
  expect(name).toBe("TransactionHistory_2023.csv");
  await expect(page.getByLabel("Format")).toHaveValue("csv");
  const text = readFileSync(file, "utf8");
  test.info().attach("csv", { body: text });
  const lines = text.trim().split(/\r?\n/);
  // Header + the 2023 rows: deposit, buy, sell, transfer.
  expect(lines).toHaveLength(5);
  expect(text).toContain("Sell");
  expect(text).toContain("Transfer");
  expect(text).not.toContain("2024-");
});
