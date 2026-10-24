// A field-by-field refusal (FastAPI's 422, its `detail` a list) is said in
// its words (#448): River's preview crashed to "Something went wrong" and
// lost every edit; the transaction form said "[object Object]".
import { test, expect, createTx, listTx, acceptDialogs, openAddForm, seedFunds, openSection } from "./fixtures";
import type { Page } from "@playwright/test";

const RIVER_CSV = [
  "Date,Sent Amount,Sent Currency,Received Amount,Received Currency,Fee Amount,Fee Currency,Tag",
  "2026-02-01 09:00:00,,,0.00002000,BTC,,,Interest", // row 2
  "2026-02-15 10:00:00,0.00100000,BTC,,,0.00000500,BTC,", // row 3: a send
].join("\n") + "\n";

function river(page: Page) {
  return page.getByRole("region", { name: "Import from River" });
}

function riverRow(page: Page, n: number) {
  return river(page).getByRole("row").filter({ has: page.getByLabel(`Include row ${n}`) });
}

test("River: a refused cost basis is said in words, and the preview keeps every edit (#448)", async ({ authedPage: page }) => {
  await seedFunds(page.request); // the send's bitcoin
  const before = (await listTx(page.request)).length;
  await page.getByRole("link", { name: "Settings" }).click();
  await openSection(page, "Import from River");
  const r = river(page);
  await r.getByLabel("River CSV file").setInputFiles({
    name: "river.csv", mimeType: "text/csv", buffer: Buffer.from(RIVER_CSV),
  });
  await r.getByRole("button", { name: "Preview" }).click();
  await expect(r.getByText("2 rows in file")).toBeVisible();

  // A thousands comma: the cell is free text, so only the server refuses it
  await riverRow(page, 2).getByLabel("Cost basis (USD)").fill("1,200");
  await riverRow(page, 3).getByLabel("Fee (BTC)").fill("0.00000600");
  const dialogs = acceptDialogs(page);
  await r.getByRole("button", { name: "Import 2 Transaction(s)" }).click();

  await expect(page.getByText("Input should be a valid decimal")).toBeVisible();
  await expect(page.getByText("Something went wrong")).toHaveCount(0);
  await expect(page.getByText("[object Object]")).toHaveCount(0);
  expect(await listTx(page.request)).toHaveLength(before);
  // The preview and both edits are still there
  await expect(riverRow(page, 2).getByLabel("Cost basis (USD)")).toHaveValue("1,200");
  await expect(riverRow(page, 3).getByLabel("Fee (BTC)")).toHaveValue("0.00000600");

  // Corrected, the same preview imports
  await riverRow(page, 2).getByLabel("Cost basis (USD)").fill("1200");
  await r.getByRole("button", { name: "Import 2 Transaction(s)" }).click();
  await expect(page.getByText(/Imported 2/i)).toBeVisible();
  expect(dialogs).toHaveLength(2);
  const all = await listTx(page.request);
  expect(all).toHaveLength(before + 2);
  expect(Number(all.find((t) => t.source === "Interest")!.cost_basis_usd)).toBe(1200);
  expect(Number(all.find((t) => t.type === "Transfer")!.fee_amount)).toBe(0.000006);
});

async function depositOf(page: Page, amount: string) {
  await page.getByLabel("Account").selectOption("Wallet");
  await page.getByLabel("Amount").fill(amount);
  await page.getByLabel("Source").selectOption("MyBTC");
  await page.getByLabel("Cost Basis (USD)").fill("0");
}

test("the form: a refused amount is said in words, on a new transaction and an edit (#448)", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill("2024-03-01T10:15:30");
  await depositOf(page, "12345678901");
  await page.getByRole("button", { name: "Save Transaction" }).click();
  await expect(page.getByText("Failed to create transaction: Amount is too large.")).toBeVisible();
  await expect(page.getByText("[object Object]")).toHaveCount(0);
  expect(await listTx(page.request)).toHaveLength(0);

  // A reload closes the form (no "Discard changes?" to answer)
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-03-01T16:15:30Z", from_account_id: 99, to_account_id: 2,
    amount: "0.01", fee_amount: "0", fee_currency: "BTC", source: "MyBTC", cost_basis_usd: "0",
  });
  await page.reload();
  await page.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Amount").fill("12345678901");
  await page.getByRole("button", { name: "Update Transaction" }).click();
  await expect(page.getByText("Failed to update transaction: Amount is too large.")).toBeVisible();
  await expect(page.getByText("[object Object]")).toHaveCount(0);
  expect((await listTx(page.request))[0]).toMatchObject({ amount: "0.01000000" });
});

test("the price card: a refused address is said in words, not a fixed sentence (#448)", async ({ authedPage: page }) => {
  await page.getByRole("link", { name: "Settings" }).click();
  await openSection(page, "Privacy & Network");
  const net = page.getByRole("region", { name: "Privacy & network" });
  await net.getByLabel(/^My own Mempool/).check();
  // Over the server's 300 characters: refused field by field
  await net.getByLabel("Your Mempool's address").fill("http://" + "a".repeat(300) + ".local");
  await net.getByRole("button", { name: "Save" }).click();
  await expect(page.getByText("String should have at most 300 characters")).toBeVisible();
  await expect(page.getByText("Could not save the choice.")).toHaveCount(0);
  expect((await (await page.request.get("/api/settings/network")).json()).price_source).not.toBe("mempool");
});
