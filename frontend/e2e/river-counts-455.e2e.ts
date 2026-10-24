// #455: the River preview counted only the rows it could read and listed
// the first ten errors, and an Import refusal named a row by its place among
// the ticked rows, not the file's row number the preview showed.
import { test, expect, acceptDialogs, openSection } from "./fixtures";
import type { Page } from "@playwright/test";

const RIVER_HEADER =
  "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag";

function river(page: Page) {
  return page.getByRole("region", { name: "Import from River" });
}

async function previewRiver(page: Page, rows: string[]) {
  await page.getByRole("link", { name: "Settings" }).click();
  await openSection(page, "Import from River");
  const r = river(page);
  await r.getByLabel("River CSV file").setInputFiles({
    name: "river.csv", mimeType: "text/csv", buffer: Buffer.from([RIVER_HEADER, ...rows].join("\n") + "\n"),
  });
  await r.getByRole("button", { name: "Preview" }).click();
}

test("River preview: every row of the file counted, every error listed (#455)", async ({ authedPage: page }) => {
  // Rows 2-13 have an unquoted thousands comma (refused); rows 14-16 are read
  const bad = Array.from({ length: 12 }, (_, i) =>
    `2024-01-${String(i + 1).padStart(2, "0")} 10:00:00,1,000.00,USD,0.01,BTC,,USD,Buy`);
  const good = [13, 14, 15].map((day) => `2024-01-${day} 10:00:00,100.00,USD,0.0025,BTC,1.00,USD,Buy`);
  await previewRiver(page, [...bad, ...good]);

  const r = river(page);
  await expect(r.getByText("15 rows in file")).toBeVisible();
  await expect(r.getByText("Errors (12):")).toBeVisible();
  const errors = r.getByRole("list", { name: "Errors" }).getByRole("listitem");
  await expect(errors).toHaveCount(12);
  await expect(errors.last()).toHaveText(/^Row 13: This row has more fields than the header/);
  await expect(r.getByRole("button", { name: "Import 3 Transaction(s)" })).toBeEnabled();
});

test("River import: a refusal names the file's row number (#455)", async ({ authedPage: page }) => {
  await previewRiver(page, [
    "2024-01-01 10:00:00,100.00,USD,0.0025,BTC,,,Buy",
    "2024-01-02 10:00:00,100.00,USD,0.0025,BTC,,,Buy",
    "2024-01-03 10:00:00,,,0.00100000,BTC,,,", //          row 4: an untagged receive
    "2024-01-04 10:00:00,0.00100000,BTC,,,0.00000500,BTC,",
  ]);
  const r = river(page);
  await expect(r.getByText("4 rows in file")).toBeVisible();
  // Row 2 left out: the receive is the second row sent, still the file's row 4
  await r.getByLabel("Include row 2").uncheck();
  const receive = r.getByRole("row").filter({ has: page.getByLabel("Include row 4") });
  await receive.getByLabel("Transaction type").selectOption("Deposit");
  await expect(receive.getByLabel("Deposit source")).toHaveValue("MyBTC");
  await expect(receive.getByLabel("Cost basis (USD)")).toHaveValue("");

  acceptDialogs(page);
  await r.getByRole("button", { name: "Import 3 Transaction(s)" }).click();
  await expect(page.getByText(/Row 4: Enter this deposit's cost basis/)).toBeVisible();
});
