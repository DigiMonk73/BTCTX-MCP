import { test, expect, USER, PASSWORD, claimAccount, loginViaUi, setupCode } from "./fixtures";

test("Create account shows only until the default login is claimed", async ({ page, app }) => {
  // Afterwards /register resets the account (every transaction deleted).
  const link = page.getByRole("link", { name: "Create account" });
  await page.goto("/login");
  await expect(link).toBeVisible();

  await claimAccount(page.request, app);
  await page.request.post("/api/logout");
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Log in" })).toBeVisible();
  await expect(link).toHaveCount(0);
});

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

test("an install still on the default login logs in with the setup code and keeps its ledger", async ({ page, app }) => {
  // An older Docker install that never changed admin/password, with data.
  const api = await page.request.post("/api/login", {
    data: { username: "admin", password: "password", setup_code: setupCode(app) },
  });
  expect(api.ok()).toBeTruthy();
  const tx = await page.request.post("/api/transactions", {
    data: {
      type: "Deposit", timestamp: "2024-01-02T12:00:00Z", from_account_id: 99, to_account_id: 1,
      amount: "1000", fee_amount: "0", fee_currency: "USD",
    },
  });
  expect(tx.ok()).toBeTruthy();
  await page.request.post("/api/logout");

  await page.goto("/login");
  await page.getByLabel("Username").fill("admin");
  await page.getByLabel("Password", { exact: true }).fill("password");
  await page.getByRole("button", { name: "Log in" }).click();
  const refused = page.getByRole("alert");
  await expect(refused).toContainText("enter the setup code");
  await expect(refused).not.toContainText("Create account");

  await page.getByLabel("Setup Code").fill(setupCode(app)!);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
  expect(await (await page.request.get("/api/transactions")).json()).toHaveLength(1);
});
