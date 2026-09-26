// The browser talks to BitcoinTX only: no font CDN, no price API, nothing
// else (prices and block height come through the backend). The page runs
// under a Content-Security-Policy of 'self'.
import { test, expect, seedKnownLedger } from "./fixtures";

test("every page loads without a single outside request, under a strict CSP", async ({ page, app }) => {
  const outside: string[] = [];
  const violations: string[] = [];
  page.on("request", (req) => {
    const url = req.url();
    if (!url.startsWith(app.url) && !url.startsWith("data:") && !url.startsWith("blob:")) outside.push(url);
  });
  page.on("console", (msg) => {
    if (/Content[- ]Security[- ]Policy/i.test(msg.text())) violations.push(msg.text());
  });

  await page.request.post("/api/users/reset-account", { data: { username: "privacy", password: "privacy-pass-1" } });
  await page.goto("/login");
  const csp = (await page.request.get("/login")).headers()["content-security-policy"];
  expect(csp).toContain("default-src 'self'");
  await page.getByLabel("Username").fill("privacy");
  await page.getByLabel("Password", { exact: true }).fill("privacy-pass-1");
  await page.getByRole("button", { name: "Log In" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await seedKnownLedger(page.request);

  for (const name of ["Dashboard", "Transactions", "Reports", "Settings"]) {
    await page.getByRole("link", { name }).click();
    await page.waitForLoadState("networkidle");
  }
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("button", { name: "Add Transaction" }).click();
  await page.getByLabel("Transaction Type").selectOption("Withdrawal");
  await page.waitForLoadState("networkidle");

  // The fonts actually came with the app.
  expect(await page.evaluate(() => document.fonts.check('16px "Inter"'))).toBe(true);
  expect(outside).toEqual([]);
  expect(violations).toEqual([]);
});
