// Every test's routes are dropped as it ends (fixtures.ts, `page` and
// `context`, #961): a route handler still asking the server when its test
// ends fails nothing, and Playwright blames no later test for it (#930).
import { test, expect } from "./fixtures";

test.describe.configure({ mode: "serial" });

test("a test that ends while its route handler is still asking the server", async ({ page }) => {
  await page.goto("/login");
  let started = false;
  await page.route("**/api/health", async (route) => {
    started = true;
    await new Promise((resolve) => setTimeout(resolve, 500)); // past the test's end
    await route.fulfill({ response: await route.fetch() });
  });
  void page.evaluate(() => fetch("/api/health").catch(() => undefined)).catch(() => undefined);
  await expect.poll(() => started).toBe(true);
});

test("the next test isn't failed by it", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Log In" })).toBeVisible();
});

test("a context's routes are dropped too", async ({ context, page }) => {
  await page.goto("/login");
  let started = false;
  await context.route("**/api/health", async (route) => {
    started = true;
    await new Promise((resolve) => setTimeout(resolve, 500));
    await route.fulfill({ response: await route.fetch() });
  });
  void page.evaluate(() => fetch("/api/health").catch(() => undefined)).catch(() => undefined);
  await expect.poll(() => started).toBe(true);
});

test("and the test after it isn't failed either", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Log In" })).toBeVisible();
});
