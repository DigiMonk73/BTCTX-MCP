// A 2.0 pre-release says so on every page, the login page included, and
// BitcoinTX Preview's first page says it starts empty beside BitcoinTX
// (#670). The build's VERSION decides: an alpha or a beta on `2.0`, so the
// banner shows; at 2.0.0 none does.
import type { Page } from "@playwright/test";
import { test, expect, PRERELEASE, VERSION, setupCode } from "./fixtures";

const banner = (page: Page) => page.getByRole("note").filter({ hasText: "a test version" });

/** The page fills the window under the banner, with nothing to scroll. */
async function fitsTheWindow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollHeight <= window.innerHeight)).toBe(true);
}

test("a server's pre-release says which test version it is on its login page", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
  if (!PRERELEASE) {
    await expect(banner(page)).toHaveCount(0);
    return;
  }
  // StartOS updates BitcoinTX in place, Docker runs it on a volume of its own: never "apart"
  await expect(banner(page)).toHaveText(`BitcoinTX · ${VERSION}: a test version, not a release`);
  expect(await banner(page).boundingBox()).toMatchObject({ x: 0, y: 0 });
  await fitsTheWindow(page);
});

test("a server's pre-release says it above every page once logged in", async ({ authedPage: page }) => {
  await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
  if (!PRERELEASE) {
    await expect(banner(page)).toHaveCount(0);
    return;
  }
  for (const tab of ["Transactions", "Reports", "Settings"]) {
    await page.getByRole("link", { name: tab, exact: true }).click();
    await expect(banner(page)).toHaveText(`BitcoinTX · ${VERSION}: a test version, not a release`);
    const header = await page.locator(".header").boundingBox();
    expect((await banner(page).boundingBox())!.y + 1).toBeLessThan(header!.y);
  }
});

test.describe("on a phone", () => {
  test.use({ viewport: { width: 360, height: 740 } });

  test("the banner wraps and the login page still fits", async ({ page }) => {
    test.skip(!PRERELEASE, "a release shows no banner");
    await page.goto("/login");
    await expect(banner(page)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await fitsTheWindow(page);
  });
});

test.describe("BitcoinTX Preview, the Mac app", () => {
  test.use({ appMode: "mac" });

  test("its first page says it starts empty beside BitcoinTX, under its own banner", async ({ page, app }) => {
    // The window's API, filled in after the page loads (desktop/desktop_api.py; auth.e2e.ts)
    await page.addInitScript((code) => {
      const api: Record<string, unknown> = {};
      Object.assign(window, { pywebview: { api } });
      window.addEventListener("load", () => setTimeout(() => {
        api.is_desktop = async () => true;
        api.setup_code = async () => code;
        window.dispatchEvent(new Event("pywebviewready"));
      }, 300));
    }, setupCode(app) ?? null);

    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Choose your username and password" })).toBeVisible();
    const line = page.getByText("is a separate test app: it starts empty");
    if (!PRERELEASE) {
      await expect(line).toHaveCount(0);
      await expect(banner(page)).toHaveCount(0);
      return;
    }
    await expect(line).toHaveText(
      "BitcoinTX Preview is a separate test app: it starts empty, and BitcoinTX and its ledger are still there, as they were.",
    );
    await expect(banner(page)).toHaveText(`BitcoinTX Preview · ${VERSION}: a test version, apart from your BitcoinTX`);
    // The default login is the Preview's, never the tester's BitcoinTX's
    await expect(page.getByText("BitcoinTX Preview still has the login it comes with (admin / password)")).toBeVisible();
  });
});
