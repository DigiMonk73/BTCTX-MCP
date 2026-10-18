// The sidebar calculator works as a pocket calculator (#450): each row of
// the issue's table pressed key by key, and its longest numbers whole on
// the display at every sidebar width.
import { test, expect } from "./fixtures";
import type { Locator, Page } from "@playwright/test";

async function press(page: Page, keys: string) {
  for (const k of keys) await page.getByRole("button", { name: k, exact: true }).click();
}

/** Whether the display's text lies inside its padding: none of it cut off. */
async function fits(display: Locator): Promise<boolean> {
  return display.evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el);
    const text = range.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return text.left >= box.left + parseFloat(style.paddingLeft) - 0.5
      && text.right <= box.right - parseFloat(style.paddingRight) + 0.5;
  });
}

test("calculator: every row of #450's table", async ({ authedPage: page }) => {
  const display = page.getByRole("status", { name: "Calculator display" });
  const rows: [keys: string, shows: string][] = [
    ["2+3+4=", "9"],
    ["5++1=", "6"],
    ["2+3=7", "7"],
    ["1.2.3+1=", "2.23"],
    [".1+.2=", "0.3"],
    ["1/0=", "Error"],
  ];
  for (const [keys, shows] of rows) {
    await press(page, `C${keys}`);
    await expect(display, keys).toHaveText(shows);
  }
});

test("calculator: the running total as the chain goes on, a second point, a new start after an error", async ({
  authedPage: page,
}) => {
  const display = page.getByRole("status", { name: "Calculator display" });
  await press(page, "2+3+");
  await expect(display).toHaveText("5");
  await press(page, "4*");
  await expect(display).toHaveText("9");
  await press(page, "2=");
  await expect(display).toHaveText("18");

  await press(page, "C1.2.3");
  await expect(display).toHaveText("1.23");

  await press(page, "C1/0=");
  await expect(display).toHaveText("Error");
  await press(page, "5+1=");
  await expect(display).toHaveText("6");
});

test("calculator: its longest numbers fit the display, in the narrow sidebar too", async ({ authedPage: page }) => {
  const display = page.getByRole("status", { name: "Calculator display" });
  const longest: [keys: string, shows: string][] = [
    ["0-999999999999999*10=", "-9999999999999990"],
    ["0-0.00000001/3=", "-0.00000000333333"],
    ["123456789012345.", "123456789012345."],
    ["999999999999999", "999999999999999"],
    ["0-9999999999999=", "-9999999999999"],
  ];
  // The wide sidebar, the narrow one (1024 px or less), and the Mac app's
  // smallest window
  for (const size of [{ width: 1440, height: 900 }, { width: 1024, height: 700 }, { width: 800, height: 600 }]) {
    await page.setViewportSize(size);
    for (const [keys, shows] of longest) {
      await press(page, `C${keys}`);
      await expect(display).toHaveText(shows);
      expect(await fits(display), `${shows} at ${size.width} px`).toBe(true);
    }
  }
});
