// Leaving the page with unsaved changes in the transaction panel asks first
// (#536): the browser's Back button and a page link get the panel's own
// "Discard changes?", a reload the browser's question. Nothing is asked
// when nothing changed or once the transaction is saved, and an answer of
// Discard changes always lets the user go.
import { test, expect, createTx, listTx, openAddForm, saveForm } from "./fixtures";
import type { Page } from "@playwright/test";

const question = (page: Page) => page.getByRole("dialog").getByRole("heading", { name: "Discard changes?" });
const addPanel = (page: Page) => page.getByRole("heading", { name: "Add Transaction" });
const dashboard = (page: Page) => page.getByRole("heading", { name: "Portfolio Overview" });

/** Whether leaving the page would get the browser's question, without leaving it. */
function leavingAsks(page: Page): Promise<boolean> {
  return page.evaluate(() => !window.dispatchEvent(new Event("beforeunload", { cancelable: true })));
}

/** Back from Transactions to the dashboard, with nothing asked. */
async function backLeaves(page: Page) {
  await page.goBack();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(dashboard(page)).toBeVisible();
  await expect(question(page)).toHaveCount(0);
}

test("Back with unsaved changes asks first: Go back keeps them, Discard changes leaves", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  await page.getByLabel("Amount").fill("100");

  await page.goBack();
  await expect(question(page)).toBeVisible();
  await expect(page).toHaveURL(/\/transactions$/);
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(question(page)).toHaveCount(0);
  await expect(page).toHaveURL(/\/transactions$/);
  await expect(page.getByLabel("Amount")).toHaveValue("100");

  // Escape on the question is Go back too
  await page.goBack();
  await expect(question(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(question(page)).toHaveCount(0);
  await expect(page.getByLabel("Amount")).toHaveValue("100");

  await page.goBack();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(dashboard(page)).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(0);

  // The history is as it was: Forward is the list again, the panel closed
  await page.goForward();
  await expect(page).toHaveURL(/\/transactions$/);
  await expect(page.getByText("No transactions found.")).toBeVisible();
  await expect(addPanel(page)).toHaveCount(0);
});

test("an edit with changes asks before a page link leaves too, and nothing is saved", async ({ authedPage: page }) => {
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-03-01T16:15:30Z", from_account_id: 99, to_account_id: 1,
    amount: "100", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  const before = await listTx(page.request);
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await page.getByLabel("Amount").fill("250");

  // The overlay covers the page links, but the keyboard still reaches them
  await page.getByRole("link", { name: "Reports" }).focus();
  await page.keyboard.press("Enter");
  await expect(question(page)).toBeVisible();
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(page).toHaveURL(/\/transactions$/);
  await expect(page.getByLabel("Amount")).toHaveValue("250");

  await page.goBack();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  expect(await listTx(page.request)).toEqual(before);
});

test("nothing is asked with nothing changed, once discarded, or once saved", async ({ authedPage: page }) => {
  // Opened, nothing typed
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("button", { name: "Add Transaction" }).click();
  await expect(addPanel(page)).toBeVisible();
  expect(await leavingAsks(page)).toBe(false);
  await backLeaves(page);

  // Changes discarded with Escape: the panel is closed and asks nothing more
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(addPanel(page)).toHaveCount(0);
  expect(await leavingAsks(page)).toBe(false);
  await backLeaves(page);

  // Saved
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill("2024-03-01T10:15:30");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  await page.getByLabel("Amount").fill("100");
  await saveForm(page);
  expect(await listTx(page.request)).toHaveLength(1);
  expect(await leavingAsks(page)).toBe(false);
  await backLeaves(page);
});

test("a reload with unsaved changes gets the browser's question", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  expect(await leavingAsks(page)).toBe(true);

  // Only the browser can ask here; its Leave answer reloads, the panel closed
  const asked: string[] = [];
  page.on("dialog", (d) => {
    asked.push(d.type());
    void d.accept();
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "Add Transaction" })).toBeVisible();
  await expect(addPanel(page)).toHaveCount(0);
  expect(asked).toEqual(["beforeunload"]);
});
