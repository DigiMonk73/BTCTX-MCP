// The import previews' messages: a cell River's Import refuses is named by
// the file's row and its column (#480), an error about the whole file is
// said without a "Row 0:" (#534), and the CSV preview counts a row once,
// however many errors it has (#479).
import { test, expect, acceptDialogs, openSection } from "./fixtures";
import type { Page } from "@playwright/test";

const RIVER_HEADER =
  "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag";
const CSV_HEADER =
  "date,type,amount,from_account,to_account,cost_basis_usd,proceeds_usd,fee_amount,fee_currency,source,purpose,notes";

function river(page: Page) {
  return page.getByRole("region", { name: "Import from River" });
}

function data(page: Page) {
  return page.getByRole("region", { name: "Data Management" });
}

async function previewRiver(page: Page, lines: string[]) {
  await page.getByRole("link", { name: "Settings" }).click();
  await openSection(page, "Import from River");
  const r = river(page);
  await r.getByLabel("River CSV file").setInputFiles({
    name: "river.csv", mimeType: "text/csv", buffer: Buffer.from(lines.join("\n") + "\n"),
  });
  await r.getByRole("button", { name: "Preview" }).click();
}

async function previewCsv(page: Page, lines: string[]) {
  await page.getByRole("link", { name: "Settings" }).click();
  await openSection(page, "Data Management");
  await data(page).getByLabel("CSV file to import").setInputFiles({
    name: "import.csv", mimeType: "text/csv", buffer: Buffer.from(lines.join("\n") + "\n"),
  });
  await data(page).getByRole("button", { name: "Preview" }).click();
  await expect(data(page).getByRole("heading", { name: "Import Preview" })).toBeVisible();
}

test("River import: a refused cell is named by the file's row and its column (#480)", async ({ authedPage: page }) => {
  await previewRiver(page, [
    RIVER_HEADER,
    "2026-02-01 09:00:00,,,0.00002000,BTC,,,Interest", // row 2: left out
    "2026-02-02 09:00:00,,,0.00003000,BTC,,,Interest", // row 3: the first row sent
  ]);
  const r = river(page);
  await expect(r.getByText("2 rows in file")).toBeVisible();
  await r.getByLabel("Include row 2").uncheck();
  const row3 = r.getByRole("row").filter({ has: page.getByLabel("Include row 3") });
  await row3.getByLabel("Cost basis (USD)").fill("1,200");
  acceptDialogs(page);
  await r.getByRole("button", { name: "Import 1 Transaction(s)" }).click();
  await expect(page.getByText("Row 3 (Cost Basis): Input should be a valid decimal")).toBeVisible();
});

test("River preview: an error about the whole file is said without a row (#534)", async ({ authedPage: page }) => {
  await previewRiver(page, ["date,type,amount", "2026-01-01,Buy,1"]);
  const errors = river(page).getByRole("list", { name: "Errors" }).getByRole("listitem");
  await expect(errors).toHaveText([/^This does not look like a River bitcoin-activity CSV\. Missing columns:/]);
});

test("CSV preview: an error about the whole file is said without a row, and is no row (#534, #479)", async ({ authedPage: page }) => {
  await previewCsv(page, [CSV_HEADER]);
  await expect(data(page).locator(".import-error-item")).toHaveText(["No valid transactions found in file."]);
  await expect(data(page).getByText("0 valid / 0 total rows")).toBeVisible();
});

test("CSV preview: a row with two errors is one row (#479)", async ({ authedPage: page }) => {
  await previewCsv(page, [CSV_HEADER, "2024-01-10T10:00:00Z,Buy,0.01,Bank,Exchange BTC,,,0.0001,BTC,,,"]);
  await expect(data(page).locator(".import-error-item")).toHaveText([
    "Row 2 (cost_basis_usd): cost_basis_usd is required for Buy transactions.",
    "Row 2 (fee_currency): Buy fee must be in USD.",
  ]);
  await expect(data(page).getByText("0 valid / 1 total rows")).toBeVisible();
});
