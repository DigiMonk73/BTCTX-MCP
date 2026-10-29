// The importer for any exchange's file (B5b, #567), in Settings' "Import
// from an exchange": a ready-made mapping's file previewed and imported, and
// another exchange's file matched, previewed and its mapping saved. The
// files are the made-up samples in testdata/exchange_files/.
import { test, expect, acceptDialogs, listTx, openSection, SAVE_ANYWAY } from "./fixtures";
import type { Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SAMPLES = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "testdata", "exchange_files");

const OTHER_EXCHANGE = [
  "Exported by Example Exchange",
  "When,Type,Coins,Dollars,Charge,Charge In,Ref,State",
  "2025-04-01 09:00,Bought,0.01000000,\"1,010.00\",10.00,USD,r-1,done",
  "2025-04-03 09:00,Withdrew,0.00200000,,0.00001000,BTC,r-3,done",
  "2025-04-04 09:00,Bought,0.01000000,\"1,010.00\",10.00,USD,r-4,waiting",
].join("\n") + "\n";

async function openImport(page: Page) {
  await page.getByRole("link", { name: "Settings" }).click();
  return openSection(page, "Import from an exchange");
}

/** Click Import of `count` rows, confirming the past-year warning when it asks (the samples' rows are dated 2025). */
async function importRows(page: Page, count: number) {
  const card = page.getByRole("region", { name: "Import from an exchange" });
  await card.getByRole("button", { name: `Import ${count} Transaction(s)` }).click();
  const saveAnyway = page.getByRole("button", { name: SAVE_ANYWAY });
  const imported = page.getByText(new RegExp(`Imported ${count} transaction`, "i"));
  await expect.poll(async () => (await saveAnyway.isVisible()) || (await imported.isVisible())).toBe(true);
  if (await saveAnyway.isVisible()) await saveAnyway.click();
  await expect(imported).toBeVisible();
}

test("a ready-made mapping's file: chosen, previewed, imported, and found again", async ({ authedPage: page }) => {
  const card = await openImport(page);
  await card.getByLabel("Exchange file").selectOption({ label: "Kraken" });
  await expect(card.getByText(/kraken\.com → profile icon → Documents → Create export → Ledgers/)).toBeVisible();
  // Built from Kraken's published format, not a real export: the owner checks the preview
  await expect(card.getByText(/not yet checked against a real one/)).toBeVisible();
  await card.getByLabel("Kraken CSV file").setInputFiles({
    name: "ledgers.csv", mimeType: "text/csv", buffer: readFileSync(join(SAMPLES, "kraken_ledgers.csv")),
  });
  await card.getByRole("button", { name: "Preview" }).click();
  await expect(card.getByText("20 rows in file")).toBeVisible();
  await expect(card.getByText("6 new")).toBeVisible();
  // Every row not read is named, with its reason
  await expect(card.getByText(/Rows 15 and 16 are ETH, not bitcoin/)).toBeVisible();
  await expect(card.getByText(/Rows 12 and 13 move coins between Kraken's own balances/)).toBeVisible();

  const dialogs = acceptDialogs(page);
  await importRows(page, 6);
  expect(dialogs).toEqual(["Import 6 transaction(s) from Kraken into your ledger?"]);
  const saved = await listTx(page.request);
  const buy = saved.find((t) => t.type === "Buy" && Number(t.amount) === 0.005)!;
  expect([Number(buy.cost_basis_usd), Number(buy.fee_amount)]).toEqual([500, 1.3]);

  // The same file again: everything is already in the ledger
  await card.getByLabel("Kraken CSV file").setInputFiles({
    name: "ledgers.csv", mimeType: "text/csv", buffer: readFileSync(join(SAMPLES, "kraken_ledgers.csv")),
  });
  await card.getByRole("button", { name: "Preview" }).click();
  await expect(card.getByText("6 already in ledger")).toBeVisible();
  await expect(card.getByText("0 new")).toBeVisible();
});

test("another exchange's file: its columns matched, previewed, and the mapping saved", async ({ authedPage: page }) => {
  const card = await openImport(page);
  await card.getByLabel("Exchange file").selectOption({ label: "Another exchange: match its columns" });
  await card.getByLabel("Exchange CSV file").setInputFiles({
    name: "example.csv", mimeType: "text/csv", buffer: Buffer.from(OTHER_EXCHANGE),
  });
  await expect(card.getByRole("table", { name: "The file's first rows" })).toContainText("1,010.00");
  // "Type", "State" and "Ref" are guessed from their names; the rest the owner says
  await expect(card.getByLabel("Kind of row", { exact: true })).toHaveValue("Type");
  await expect(card.getByRole("status")).toHaveText("Still to match: Date, Bitcoin amount.");
  await expect(card.getByRole("button", { name: "Preview" })).toBeDisabled();
  await card.getByLabel("Date", { exact: true }).selectOption("When");
  await card.getByLabel("Bitcoin amount", { exact: true }).selectOption("Coins");
  await card.getByLabel("Dollar amount (if any)", { exact: true }).selectOption("Dollars");
  await card.getByLabel("Fee (if any)", { exact: true }).selectOption("Charge");
  await card.getByLabel("Fee currency (if any)", { exact: true }).selectOption("Charge In");
  await card.getByLabel("“Bought” is").selectOption("buy");
  await card.getByLabel("“Withdrew” is").selectOption("send");
  await card.getByLabel("done", { exact: true }).check();
  await card.getByLabel("A buy's dollars include its fee (the total paid)").check();

  await card.getByRole("button", { name: "Preview" }).click();
  await expect(card.getByText("3 rows in file")).toBeVisible();
  await expect(card.getByText("2 new")).toBeVisible();
  await expect(card.getByText(/Row 5 is waiting, not completed/)).toBeVisible();

  await card.getByLabel("Mapping's name").fill("Example Exchange");
  await card.getByRole("button", { name: "Save this mapping" }).click();
  await expect(page.getByText("Saved “Example Exchange”.")).toBeVisible();
  await expect(card.getByLabel("Exchange file")).toHaveValue(/^own-\d+$/);
  await expect(card.getByLabel("Exchange file").locator("option", { hasText: "Example Exchange" })).toHaveCount(1);

  const dialogs = acceptDialogs(page);
  await card.getByRole("button", { name: "Preview" }).click();
  await importRows(page, 2);
  expect(dialogs).toEqual(["Import 2 transaction(s) from Example Exchange into your ledger?"]);
  const buy = (await listTx(page.request)).find((t) => t.type === "Buy")!;
  // 1,010.00 paid with its 10.00 fee in it: 1,000.00 bought the coins
  expect([Number(buy.cost_basis_usd), Number(buy.fee_amount)]).toEqual([1000, 10]);
});
