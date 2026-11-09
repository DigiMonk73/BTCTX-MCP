// A password change ends every other browser's session (SECURITY-RULES.md,
// "Sessions"): that browser's next click goes to the sign-in page, rather
// than show load errors, and Settings' reset form never says "No user
// found to reset credentials." (#919).
import type { Browser, Page } from "@playwright/test";
import { test, expect, PASSWORD, acceptDialogs, loginViaUi, openSection, type App } from "./fixtures";

const NEW_PASSWORD = "e2e-new-password-456";

/** A second browser, logged in, on the page its link `on` opens. */
async function otherBrowser(browser: Browser, app: App, on: string): Promise<Page> {
  const context = await browser.newContext({ baseURL: app.url });
  const page = await context.newPage();
  await loginViaUi(page);
  await page.getByRole("link", { name: on }).click();
  await expect(page).toHaveURL(new RegExp(`/${on.toLowerCase()}$`));
  return page;
}

/** The password changed in Settings › Account, as the owner would. */
async function changePassword(page: Page) {
  acceptDialogs(page);
  await page.getByRole("link", { name: "Settings" }).click();
  const account = await openSection(page, "Account");
  await account.getByLabel("New password").fill(NEW_PASSWORD);
  await account.getByLabel("Current password").fill(PASSWORD);
  await account.getByRole("button", { name: "Update" }).click();
  await expect(page.getByText("Credentials updated successfully.")).toBeVisible();
}

for (const to of ["Transactions", "Dashboard", "Settings"]) {
  test(`after a password change in another browser, ${to} goes to the sign-in page`, async ({ authedPage: page, browser, app }) => {
    test.fail(); // #919: load errors until its fix
    const other = await otherBrowser(browser, app, "Reports");
    try {
      await changePassword(page);
      await other.getByRole("link", { name: to }).click();
      await expect(other).toHaveURL(/\/login$/);
      await expect(other.getByRole("button", { name: "Log In" })).toBeVisible();
    } finally {
      await other.context().close();
    }
  });
}

test("Settings' reset form in another browser goes to the sign-in page", async ({ authedPage: page, browser, app }) => {
  test.fail(); // #919: "No user found to reset credentials." until its fix
  const other = await otherBrowser(browser, app, "Settings");
  try {
    const form = await openSection(other, "Account");
    await changePassword(page);
    acceptDialogs(other);
    await form.getByLabel("New username").fill("another-name");
    await form.getByLabel("Current password").fill(PASSWORD);
    await form.getByRole("button", { name: "Update" }).click();
    await expect(other).toHaveURL(/\/login$/);
  } finally {
    await other.context().close();
  }
});
