// The transaction panel takes the keyboard (#772): it's a named modal
// dialog, focus moves into it as it opens, Tab and Shift+Tab stay in it,
// and focus goes back to what opened it as it closes, as the dialogs do.
import { type Locator, type Page } from "@playwright/test";
import { createTx, expect, seedFunds, test } from "./fixtures";

const holdsFocus = (panel: Locator) => panel.evaluate((el) => el.contains(document.activeElement));

async function openByKeyboard(page: Page) {
  await page.goto("/transactions");
  const add = page.getByRole("button", { name: "Add transaction" });
  await add.focus();
  await page.keyboard.press("Enter");
  const panel = page.getByRole("dialog", { name: "Add Transaction" });
  await expect(panel).toBeVisible();
  await expect.poll(() => holdsFocus(panel)).toBe(true);
  return { add, panel };
}

test("the panel takes the keyboard as it opens, keeps it, and gives it back on Escape", async ({ authedPage: page }) => {
  const { add, panel } = await openByKeyboard(page);
  // Polled: in WebKit (Safari tabs to text fields only) the trap brings focus back a moment after the Tab
  const reached = new Set<string>();
  for (const key of [...Array(30).fill("Tab"), ...Array(10).fill("Shift+Tab")]) {
    await page.keyboard.press(key);
    await expect.poll(() => holdsFocus(panel), { message: `after ${key}` }).toBe(true);
    reached.add(await page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.id ?? ""));
  }
  expect(reached.has("Close")).toBe(true); // Tab moved focus round the panel's controls, not left it pinned
  expect(reached.size).toBeGreaterThan(1);
  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
  await expect(add).toBeFocused();
});

test("after a save, the keyboard is back on the button that opened the panel", async ({ authedPage: page }) => {
  const { add, panel } = await openByKeyboard(page);
  await panel.getByLabel("Transaction Type").selectOption("Deposit");
  await panel.getByLabel("Account", { exact: true }).selectOption({ label: "Bank" });
  await panel.getByLabel("Amount", { exact: true }).fill("100");
  await panel.getByRole("button", { name: "Save transaction" }).click();
  await expect(panel).toHaveCount(0);
  await expect(add).toBeFocused();
});

test("Discard changes? takes the keyboard on Go back, keeps it, and gives it back to the panel", async ({
  authedPage: page,
}) => {
  const { panel } = await openByKeyboard(page);
  const type = panel.getByLabel("Transaction Type");
  await type.selectOption("Deposit");
  const amount = panel.getByLabel("Amount", { exact: true });
  await amount.fill("100"); // a change to lose
  await amount.focus();
  await page.keyboard.press("Escape");
  const question = page.getByRole("dialog", { name: "Discard changes?" });
  await expect(question.getByRole("button", { name: "Go back" })).toBeFocused();
  for (const key of ["Tab", "Tab", "Tab", "Shift+Tab", "Shift+Tab"]) {
    await page.keyboard.press(key);
    await expect.poll(() => holdsFocus(question), { message: `after ${key}` }).toBe(true);
  }
  await page.keyboard.press("Escape"); // its safe answer: Go back
  await expect(question).toHaveCount(0);
  await expect(amount).toBeFocused();
});

test("after an edit is saved, its row reloaded away, the keyboard is on Add transaction", async ({
  authedPage: page,
}) => {
  await seedFunds(page.request);
  await createTx(page.request, {
    type: "Deposit", timestamp: "2026-01-05T12:00:00Z", to_account_id: 1, from_account_id: 99,
    amount: "50", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  await page.goto("/transactions");
  await page.getByLabel("Sort transactions").selectOption("CREATION_DESC");
  // Opened by the keyboard, so Edit is what opened it in every engine: a click focuses no button in
  // WebKit, and Linux WebKit's focus stayed on the Sort select, where it then went back (#793)
  const edit = page.getByRole("listitem").first().getByRole("button", { name: "Edit" });
  await edit.focus();
  await page.keyboard.press("Enter");
  const panel = page.getByRole("dialog", { name: "Edit Transaction" });
  await panel.getByLabel("Amount", { exact: true }).fill("60");
  await panel.getByRole("button", { name: "Update transaction" }).click();
  await expect(panel).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Add transaction" })).toBeFocused();
});
