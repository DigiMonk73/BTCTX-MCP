import { request as playwrightRequest, type Page } from "@playwright/test";
import { test, expect, USER, PASSWORD, claimAccount, createTx, loginViaUi, setupCode, type App } from "./fixtures";

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
  // A fresh install has nothing to delete: no warning at all (#256)
  expect(dialogs).toEqual([]);
  await expect(page.getByText("Registration successful!")).toBeVisible();

  // The code is used up; the default credentials no longer work; the new ones do.
  expect(setupCode(app)).toBeUndefined();
  const old = await page.request.post("/api/login", { data: { username: "admin", password: "password" } });
  expect(old.status()).toBe(401);
  await loginViaUi(page);
  await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
});

test("Create account on an install with transactions: the code first, then the dialog (#256)", async ({ page, app }) => {
  // An older install never taken off admin/password, with a transaction
  const r = await page.request.post("/api/login", {
    data: { username: "admin", password: "password", setup_code: setupCode(app) },
  });
  expect(r.ok()).toBeTruthy();
  const tx = await page.request.post("/api/transactions", {
    data: {
      type: "Deposit", timestamp: "2024-01-02T18:00:00Z", from_account_id: 99, to_account_id: 1,
      amount: "1000", fee_amount: "0", fee_currency: "USD",
    },
  });
  expect(tx.ok()).toBeTruthy();
  await page.request.post("/api/logout");

  await page.goto("/register");
  await page.getByLabel("New Username").fill(USER);
  await page.getByLabel("New Password").fill(PASSWORD);
  await page.getByLabel("Setup Code").fill("AAAA-AAAA-AAAA");
  await page.getByRole("button", { name: "Register" }).click();
  await expect(page.getByRole("alert")).toContainText("That setup code is wrong.");
  await expect(page.getByRole("dialog")).toHaveCount(0);

  await page.getByLabel("Setup Code").fill(setupCode(app)!);
  await page.getByRole("button", { name: "Register" }).click();
  const dialog = page.getByRole("dialog", { name: "Create a new account and delete every transaction?" });
  await expect(dialog).toContainText("This deletes 1 transaction, 2024");
  // Not logged in: the backup is a login away
  await expect(dialog.getByRole("button", { name: "Download a backup first" })).toHaveCount(0);
  await expect(dialog.getByRole("link", { name: "Log in" })).toBeVisible();
  await dialog.getByRole("button", { name: "Cancel" }).click();
  expect((await (await page.request.get("/api/users/setup-status")).json()).is_default).toBe(true);

  await page.getByRole("button", { name: "Register" }).click();
  await dialog.getByLabel("Type DELETE to confirm").fill("DELETE");
  await dialog.getByRole("button", { name: "Delete 1 transaction" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText(/A copy of the database from before is kept/)).toBeVisible();
  await loginViaUi(page);
  expect(await (await page.request.get("/api/transactions")).json()).toHaveLength(0);
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

test("on a phone every header tab, Logout too, is on screen without scrolling", async ({ authedPage: page }) => {
  // The 1.2.3 VM walk: at 375px the header was 407px wide and Logout read "Logo".
  for (const width of [375, 430]) {
    await page.setViewportSize({ width, height: 800 });
    const header = page.locator(".header");
    const { scrollWidth, clientWidth } = await header.evaluate((h) => ({ scrollWidth: h.scrollWidth, clientWidth: h.clientWidth }));
    expect(scrollWidth, `${width}px`).toBeLessThanOrEqual(clientWidth);
    const logout = await page.getByRole("link", { name: "Logout" }).boundingBox();
    expect(logout!.x + logout!.width, `${width}px`).toBeLessThanOrEqual(width);
  }
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

test("a login leaves the tax timezone alone once the ledger has transactions (#334)", async ({ page, app }, info) => {
  // A ledger used so far only from a browser that reports UTC (Tor Browser): no timezone ever chosen
  await claimAccount(page.request, app);
  expect((await page.request.post("/api/login", { data: { username: USER, password: PASSWORD } })).ok()).toBeTruthy();
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-01-02T12:00:00Z", from_account_id: 99, to_account_id: 1,
    amount: "1000", fee_amount: "0", fee_currency: "USD",
  });
  await page.request.post("/api/logout");

  // Another timezone would recalculate past years: only Settings changes it, where it's suggested
  await loginViaUi(page);
  const tz = await (await page.request.get("/api/settings/tax-timezone")).json();
  expect(tz).toEqual({ timezone: "UTC", source: "default" });
  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByRole("note").filter({ hasText: "No tax timezone has been chosen" }))
    .toContainText(`This computer is set to ${info.project.use.timezoneId}: if that's where you file`);
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
  // A server's code is in its log (the Mac app's text only on the Mac, #258)
  await expect(page.locator("#login-setup-code-hint")).toContainText("docker logs");
  await expect(page.locator("#login-setup-code-hint")).not.toContainText("Application Support");
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

test.describe("the Mac app", () => {
  test.use({ appMode: "mac" });

  /** The window's API as desktop/desktop_api.py gives it: window.pywebview
   * may be there before the page's own code runs, but pywebview fills in its
   * methods only after the page loads, then fires "pywebviewready". */
  async function asTheAppWindow(page: Page, code: string | undefined, withSetupCode = true) {
    await page.addInitScript(([c, has]) => {
      const api: Record<string, unknown> = {};
      Object.assign(window, { pywebview: { api } });
      window.addEventListener("load", () => setTimeout(() => {
        api.is_desktop = async () => true;
        if (has) api.setup_code = async () => c ?? null;
        window.dispatchEvent(new Event("pywebviewready"));
      }, 300));
    }, [code, withSetupCode] as const);
  }

  /** An older Mac install never taken off admin/password, with a transaction. */
  async function ledgerOnTheDefaultLogin(page: Page, app: App) {
    const r = await page.request.post("/api/login", {
      data: { username: "admin", password: "password", setup_code: setupCode(app) },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    const tx = await page.request.post("/api/transactions", {
      data: {
        type: "Deposit", timestamp: "2024-01-02T12:00:00Z", from_account_id: 99, to_account_id: 1,
        amount: "1000", fee_amount: "0", fee_currency: "USD",
      },
    });
    expect(tx.ok()).toBeTruthy();
    await page.request.post("/api/logout");
  }

  test("its window has the owner choose a username and password, and keeps the ledger", async ({ page, app }, info) => {
    await ledgerOnTheDefaultLogin(page, app);
    await asTheAppWindow(page, setupCode(app));

    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Choose your username and password" })).toBeVisible();
    await expect(page.getByLabel("Setup Code")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "Create account" })).toHaveCount(0);
    await expect(page.getByText("your transactions are kept")).toBeVisible();

    // Checked before anything is sent
    await page.getByLabel("New Username").fill(USER);
    await page.getByLabel("New Password", { exact: true }).fill(PASSWORD);
    await page.getByLabel("Repeat New Password").fill(PASSWORD + "x");
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("alert")).toHaveText("The two passwords don't match.");
    expect(setupCode(app)).toBeDefined();

    await page.getByLabel("Repeat New Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Continue" }).click();
    await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();

    // The ledger is kept; the code is used up; the default login no longer works, the new one does
    expect(await (await page.request.get("/api/transactions")).json()).toHaveLength(1);
    expect(setupCode(app)).toBeUndefined();
    const other = await playwrightRequest.newContext({ baseURL: app.url });
    expect((await other.post("/api/login", { data: { username: "admin", password: "password" } })).status()).toBe(401);
    expect((await other.post("/api/login", { data: { username: USER, password: PASSWORD } })).status()).toBe(200);
    await other.dispose();
    // A ledger with transactions keeps its tax timezone at a login (#334): Settings suggests the computer's
    const tz = await (await page.request.get("/api/settings/tax-timezone")).json();
    expect(tz).toEqual({ timezone: "UTC", source: "default" });
    await page.getByRole("link", { name: "Settings" }).click();
    await expect(page.getByRole("note").filter({ hasText: "No tax timezone has been chosen" }))
      .toContainText(`This computer is set to ${info.project.use.timezoneId}`);
  });

  test("a window that can't read its setup code offers the sign-in form with the typed code", async ({ page, app }) => {
    await asTheAppWindow(page, undefined);  // setup_code() gives nothing
    await page.goto("/login");
    await expect(page.getByRole("alert")).toContainText("couldn't read its setup code");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password", { exact: true }).fill("password");
    await page.getByLabel("Setup Code").fill(setupCode(app)!);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
  });

  test("in a browser, without the window, the default login needs the typed setup code", async ({ page }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(page.getByLabel("Setup Code")).toBeVisible();
    // Where the code is on a Mac, not a server's log (#258)
    const hint = page.locator("#login-setup-code-hint");
    await expect(hint).toContainText("Application Support/BitcoinTX");
    await expect(hint).not.toContainText("docker logs");
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password", { exact: true }).fill("password");
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page.getByRole("alert")).toContainText("enter the setup code");
    await expect(page.getByRole("alert")).toContainText("Application Support/BitcoinTX");
    await expect(page).toHaveURL(/\/login$/);
    const claim = await page.request.post("/api/users/reset-account", { data: { username: USER, password: PASSWORD } });
    expect(claim.status()).toBe(403);
    expect((await (await page.request.get("/api/users/setup-status")).json()).is_default).toBe(true);
  });

  test("in a browser, Create account says where the Mac app keeps the setup code", async ({ page }) => {
    await page.goto("/register");
    const hint = page.locator("#setup-code-hint");
    await expect(hint).toContainText("Application Support/BitcoinTX");
    await expect(hint).not.toContainText("docker logs");
  });

  test("on the default login, Settings says where the Mac app keeps the setup code", async ({ page, app }) => {
    const r = await page.request.post("/api/login", {
      data: { username: "admin", password: "password", setup_code: setupCode(app) },
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    await page.goto("/settings");
    const hint = page.getByText("This is still the default login");
    await expect(hint).toContainText("Application Support/BitcoinTX");
    await expect(hint).not.toContainText("docker logs");
  });

  test("a window that can't supply the code offers the typed field and says where it is", async ({ page, app }) => {
    await asTheAppWindow(page, setupCode(app), false);
    await page.goto("/login");
    await expect(page.getByText("setup-code.txt in BitcoinTX's data folder")).toBeVisible();
    await expect(page.getByText("set your own username and password in Settings")).toBeVisible();
    await page.getByLabel("Username").fill("admin");
    await page.getByLabel("Password", { exact: true }).fill("password");
    await page.getByLabel("Setup Code").fill(setupCode(app)!);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page.getByRole("heading", { name: "Portfolio Overview" })).toBeVisible();
  });
});
