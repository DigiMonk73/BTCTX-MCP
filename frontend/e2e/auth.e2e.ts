import { test, expect, USER, PASSWORD, claimAccount, loginViaUi, setupCode } from "./fixtures";

test("first run: claim the default account, then log in", async ({ page, app }) => {
  const dialogs: string[] = [];
  page.on("dialog", (d) => {
    dialogs.push(d.message());
    void d.accept();
  });

  await page.goto("/register");
  await expect(page.getByRole("heading", { name: "Register Account" })).toBeVisible();
  // A fresh install still has the default login: no current password asked,
  // but the setup code from the server's log / data folder, and the rule.
  await expect(page.getByLabel("Current Password")).toHaveCount(0);
  await expect(page.getByText("At least 12 characters.")).toBeVisible();
  await expect(page.getByText("setup-code.txt in the data folder")).toBeVisible();

  // "admin" is reserved.
  await page.getByLabel("New Username").fill("admin");
  await page.getByLabel("New Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByText("The username 'admin' is reserved")).toBeVisible();
  expect(dialogs).toHaveLength(0);

  // Too short a password, then no setup code: refused before anything is sent.
  await page.getByLabel("New Username").fill(USER);
  await page.getByLabel("New Password").fill("elevenchars");
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByText("The new password is too short.")).toBeVisible();
  await page.getByLabel("New Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByRole("alert")).toContainText("Enter the setup code.");
  expect(dialogs).toHaveLength(0);

  // A wrong code: the server says so.
  await page.getByLabel("Setup Code").fill("AAAA-AAAA-AAAA");
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByRole("alert")).toContainText("That setup code is wrong.");
  dialogs.length = 0;

  const code = setupCode(app);
  expect(code).toMatch(/^[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$/);
  await page.getByLabel("Setup Code").fill(code!);
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(dialogs).toEqual([
    "This will update your username and password and delete any existing transactions. Continue?",
  ]);
  await expect(page.getByText("Registration successful!")).toBeVisible();

  // The code is used up; the default credentials no longer work; the new ones do.
  expect(setupCode(app)).toBeUndefined();
  const old = await page.request.post("/api/login", { data: { username: "admin", password: "password" } });
  expect(old.status()).toBe(401);
  await loginViaUi(page);
  await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
});

test("register again once claimed needs the current password", async ({ page, app }) => {
  await claimAccount(page.request, app);
  await page.goto("/register");
  await expect(page.getByLabel("Current Password")).toBeVisible();
});

test("wrong password is rejected with a message", async ({ page, app }) => {
  await claimAccount(page.request, app);
  await page.goto("/login");
  await page.getByLabel("Username").fill(USER);
  await page.getByLabel("Password", { exact: true }).fill("not-the-password");
  await page.getByRole("button", { name: "Log In" }).click();
  await expect(page.locator(".login-error-msg")).toBeVisible();
  await expect(page).toHaveURL(/\/login$/);
});

test("show and hide the password", async ({ page }) => {
  await page.goto("/login");
  const field = page.getByLabel("Password", { exact: true });
  await field.fill("secret");
  await expect(field).toHaveAttribute("type", "password");
  await page.getByRole("button", { name: "Show Password" }).click();
  await expect(field).toHaveAttribute("type", "text");
  await page.getByRole("button", { name: "Hide Password" }).click();
  await expect(field).toHaveAttribute("type", "password");
});

test("protected pages send you to login", async ({ page }) => {
  for (const path of ["/dashboard", "/transactions", "/reports", "/settings"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login$/);
  }
});

test("logout from the header", async ({ authedPage: page }) => {
  page.on("dialog", (d) => {
    expect(d.message()).toBe("Are you sure you want to log out?");
    void d.accept();
  });
  await page.getByRole("link", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/transactions")).status()).toBe(401);
});

test("logout from Settings", async ({ authedPage: page }) => {
  page.on("dialog", (d) => void d.accept());
  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect((await page.request.get("/api/transactions")).status()).toBe(401);
});

test("cancelling the logout dialog keeps you logged in", async ({ authedPage: page }) => {
  page.on("dialog", (d) => void d.dismiss());
  await page.getByRole("link", { name: "Logout" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  expect((await page.request.get("/api/transactions")).status()).toBe(200);
});

test("login sets the tax timezone to the computer's zone", async ({ authedPage: page }, info) => {
  const tz = info.project.use.timezoneId;
  const r = await page.request.get("/api/settings/tax-timezone");
  expect((await r.json()).timezone).toBe(tz);
});
