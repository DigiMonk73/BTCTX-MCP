// The transaction panel takes the keyboard (#772): it's a named modal
// dialog, focus moves into it as it opens, Tab and Shift+Tab stay in it,
// and focus goes back to what opened it as it closes, as the dialogs do.
import { type Locator, type Page } from "@playwright/test";
import { expect, test } from "./fixtures";

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
  for (const key of [...Array(30).fill("Tab"), ...Array(10).fill("Shift+Tab")]) {
    await page.keyboard.press(key);
    expect(await holdsFocus(panel), `after ${key}`).toBe(true);
  }
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
