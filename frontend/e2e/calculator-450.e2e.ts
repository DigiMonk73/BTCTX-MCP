// The sidebar calculator works as a pocket calculator (#450): each row of
// the issue's table, pressed key by key.
import { test, expect } from "./fixtures";
import type { Page } from "@playwright/test";

async function press(page: Page, keys: string) {
  for (const k of keys) await page.getByRole("button", { name: k, exact: true }).click();
}

const ROWS: [keys: string, shows: string][] = [
  ["2+3+4=", "9"],
  ["5++1=", "6"],
  ["1.2.3+1=", "2.23"],
  [".1+.2=", "0.3"],
  ["1/0=", "Error"],
];

for (const [keys, shows] of ROWS) {
  test(`calculator: ${keys} shows ${shows}`, async ({ authedPage: page }) => {
    const display = page.getByRole("status", { name: "Calculator display" });
    await press(page, keys);
    await expect(display).toHaveText(shows);
  });
}

test("calculator: the running total shows as the chain goes on", async ({ authedPage: page }) => {
  const display = page.getByRole("status", { name: "Calculator display" });
  await press(page, "2+3+");
  await expect(display).toHaveText("5");
  await press(page, "4*");
  await expect(display).toHaveText("9");
  await press(page, "2=");
  await expect(display).toHaveText("18");
});

test("calculator: a digit after = starts a new number", async ({ authedPage: page }) => {
  const display = page.getByRole("status", { name: "Calculator display" });
  await press(page, "2+3=");
  await expect(display).toHaveText("5");
  await press(page, "7");
  await expect(display).toHaveText("7");
});

test("calculator: a second point is ignored as it's typed", async ({ authedPage: page }) => {
  const display = page.getByRole("status", { name: "Calculator display" });
  await press(page, "1.2.3");
  await expect(display).toHaveText("1.23");
});

test("calculator: after an error, a digit starts again", async ({ authedPage: page }) => {
  const display = page.getByRole("status", { name: "Calculator display" });
  await press(page, "1/0=");
  await expect(display).toHaveText("Error");
  await press(page, "5+1=");
  await expect(display).toHaveText("6");
});
