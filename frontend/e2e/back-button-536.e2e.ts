// Leaving the page with unsaved changes in the transaction panel asks first
// (#536): the browser's Back button, a page link and Logout get the panel's
// own "Discard changes?", a reload the browser's question. Nothing is asked
// when nothing changed or once the transaction is saved, and an answer of
// Discard changes always lets the user go.
import { test, expect, createTx, listTx, openAddForm, saveForm } from "./fixtures";
import type { Locator, Page } from "@playwright/test";

const question = (page: Page) => page.getByRole("dialog").getByRole("heading", { name: "Discard changes?" });
const addPanel = (page: Page) => page.getByRole("heading", { name: "Add Transaction" });
const dashboard = (page: Page) => page.getByRole("heading", { name: "Portfolio Overview" });

/** Whether leaving the page would get the browser's question, without leaving it. */
function leavingAsks(page: Page): Promise<boolean> {
  return page.evaluate(() => !window.dispatchEvent(new Event("beforeunload", { cancelable: true })));
}

/** How many logouts the page has sent so far. */
function logoutsSent(page: Page): () => number {
  let sent = 0;
  page.on("request", (r) => {
    if (r.url().endsWith("/api/logout")) sent++;
  });
  return () => sent;
}

/** Whether the browser's session is still logged in. */
async function loggedIn(page: Page): Promise<boolean> {
  return (await page.request.get("/api/transactions")).status() === 200;
}

/**
 * The link pressed with the card's settings held back until then, so the
 * link shows first (a slow server, or 1 run in 40); the card then gets the
 * keyboard (#612).
 */
async function pressedBeforeTheCard(page: Page, link: Locator, title: Locator) {
  let answer = () => {};
  const pressedFirst = new Promise<void>((go) => (answer = go));
  await page.route("**/api/settings/network", async (route) => {
    await pressedFirst;
    await route.continue();
  });
  await page.goto("/dashboard");
  await link.focus();
  await page.keyboard.press("Enter");
  await expect(title).toHaveCount(0);
  answer();
  await expect(title).toBeFocused();
  await expect(title).toBeInViewport();
  await expect(page).toHaveURL(/\/dashboard$/);
}

/** Back from Transactions to the dashboard, with nothing asked. */
async function backLeaves(page: Page) {
  await page.goBack();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(dashboard(page)).toBeVisible();
  await expect(question(page)).toHaveCount(0);
}

test("Back with unsaved changes asks first: Go back keeps them, Discard changes leaves", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  await page.getByLabel("Amount").fill("100");

  await page.goBack();
  await expect(question(page)).toBeVisible();
  await expect(page).toHaveURL(/\/transactions$/);
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(question(page)).toHaveCount(0);
  await expect(page).toHaveURL(/\/transactions$/);
  await expect(page.getByLabel("Amount")).toHaveValue("100");

  // Escape on the question is Go back too
  await page.goBack();
  await expect(question(page)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(question(page)).toHaveCount(0);
  await expect(page.getByLabel("Amount")).toHaveValue("100");

  await page.goBack();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(dashboard(page)).toBeVisible();
  expect(await listTx(page.request)).toHaveLength(0);

  // The history is as it was: Forward is the list again, the panel closed
  await page.goForward();
  await expect(page).toHaveURL(/\/transactions$/);
  await expect(page.getByText("No transactions found.")).toBeVisible();
  await expect(addPanel(page)).toHaveCount(0);
});

test("an edit with changes asks before a page link leaves too, and nothing is saved", async ({ authedPage: page }) => {
  await createTx(page.request, {
    type: "Deposit", timestamp: "2024-03-01T16:15:30Z", from_account_id: 99, to_account_id: 1,
    amount: "100", fee_amount: "0", fee_currency: "USD", source: "N/A",
  });
  const before = await listTx(page.request);
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("listitem").first().getByRole("button", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Edit Transaction" })).toBeVisible();
  await page.getByLabel("Amount").fill("250");

  // The overlay covers the page links, but the keyboard still reaches them
  await page.getByRole("link", { name: "Reports" }).focus();
  await page.keyboard.press("Enter");
  await expect(question(page)).toBeVisible();
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(page).toHaveURL(/\/transactions$/);
  await expect(page.getByLabel("Amount")).toHaveValue("250");

  await page.goBack();
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  expect(await listTx(page.request)).toEqual(before);
});

test("nothing is asked with nothing changed, once discarded, or once saved", async ({ authedPage: page }) => {
  // Opened, nothing typed
  await page.getByRole("link", { name: "Transactions" }).click();
  await page.getByRole("button", { name: "Add Transaction" }).click();
  await expect(addPanel(page)).toBeVisible();
  expect(await leavingAsks(page)).toBe(false);
  await backLeaves(page);

  // Changes discarded with Escape: the panel is closed and asks nothing more
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(addPanel(page)).toHaveCount(0);
  expect(await leavingAsks(page)).toBe(false);
  await backLeaves(page);

  // Saved
  await openAddForm(page, "Deposit");
  await page.getByLabel("Date & Time").fill("2024-03-01T10:15:30");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  await page.getByLabel("Amount").fill("100");
  await saveForm(page);
  expect(await listTx(page.request)).toHaveLength(1);
  expect(await leavingAsks(page)).toBe(false);
  await backLeaves(page);
});

test("a reload with unsaved changes gets the browser's question", async ({ authedPage: page }) => {
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  expect(await leavingAsks(page)).toBe(true);

  // Only the browser can ask here; its Leave answer reloads, the panel closed
  const asked: string[] = [];
  page.on("dialog", (d) => {
    asked.push(d.type());
    void d.accept();
  });
  await page.reload();
  await expect(page.getByRole("button", { name: "Add Transaction" })).toBeVisible();
  await expect(addPanel(page)).toHaveCount(0);
  expect(asked).toEqual(["beforeunload"]);
});

test("Logout with unsaved changes asks Discard changes? first, and sends nothing before the answer", async ({
  authedPage: page,
}) => {
  const browserAsked: string[] = [];
  page.on("dialog", (d) => {
    browserAsked.push(d.message());
    void d.accept();
  });
  const logouts = logoutsSent(page);
  await openAddForm(page, "Deposit");
  await page.getByLabel("Account", { exact: true }).selectOption("Bank");
  const logout = page.getByRole("link", { name: "Logout" });

  // Under the overlay, but the keyboard reaches it
  await logout.focus();
  await page.keyboard.press("Enter");
  await expect(question(page)).toBeVisible();
  await page.getByRole("button", { name: "Go back" }).click();
  await expect(question(page)).toHaveCount(0);
  await expect(page.getByLabel("Account", { exact: true }).locator("option:checked")).toHaveText("Bank");
  expect(await loggedIn(page)).toBe(true);
  expect(logouts()).toBe(0);

  await logout.focus();
  await page.keyboard.press("Enter");
  await page.getByRole("button", { name: "Discard changes" }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect(await loggedIn(page)).toBe(false);
  expect(logouts()).toBe(1);
  expect(browserAsked).toEqual([]); // one question, the panel's: not "Are you sure…?" as well
});

test("a link from another site to /logout doesn't log out", async ({ authedPage: page, app }) => {
  // The POST would come from BitcoinTX's own page, so the server's cross-site
  // refusal never sees it: only the Header's Logout may ask for it
  const logouts = logoutsSent(page);
  await page.route("http://elsewhere.invalid/", (route) =>
    route.fulfill({ contentType: "text/html", body: `<a href="${app.url}/logout">Log out of BitcoinTX</a>` }),
  );
  await page.goto("http://elsewhere.invalid/");
  await page.getByRole("link", { name: "Log out of BitcoinTX" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(dashboard(page)).toBeVisible();
  expect(await loggedIn(page)).toBe(true);
  expect(logouts()).toBe(0);
});

test("the Header's Logout logs out once: Forward onto its /logout never again", async ({ authedPage: page }) => {
  page.on("dialog", (d) => void d.accept()); // its "Are you sure…?": nothing changed
  const logouts = logoutsSent(page);
  // The answer held back, so Back can leave /logout before it comes, and its
  // entry stays in the history
  let answer!: () => void;
  const answered = new Promise<void>((resolve) => (answer = resolve));
  await page.route("**/api/logout", async (route) => {
    await answered;
    await route.continue();
  });

  const sent = page.waitForRequest("**/api/logout");
  await page.getByRole("link", { name: "Logout" }).click();
  await sent;
  await expect(page).toHaveURL(/\/logout$/);
  await page.goBack();
  answer();
  await expect(page).toHaveURL(/\/login$/);
  expect(await loggedIn(page)).toBe(false);

  await page.goForward();
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "Log In" })).toBeVisible();
  expect(logouts()).toBe(1);
});

test.describe("no price source chosen yet: the price card's link", () => {
  test.use({ priceSource: "unset" });
  const link = (page: Page) => page.getByRole("link", { name: "Choose a source" });

  test("leaves no history entry of the browser's own, so Back from unsaved changes still asks", async ({
    authedPage: page,
  }) => {
    // An entry the router didn't make: it can't undo a Back onto one
    await link(page).click();
    await openAddForm(page, "Deposit");
    await page.getByLabel("Account", { exact: true }).selectOption("Bank");
    await page.goBack();
    await expect(question(page)).toBeVisible();
    await page.getByRole("button", { name: "Discard changes" }).click();
    await expect(page).toHaveURL(/\/dashboard$/);
    await expect(dashboard(page)).toBeVisible();
  });

  test("still goes to the card, the keyboard with it", async ({ authedPage: page }) => {
    const title = page.getByRole("heading", { name: "Bitcoin prices" });
    // The card shows once its settings load, maybe after the link (#793: about 1 run in 40 was faster)
    await expect(title).toBeVisible();
    await link(page).focus();
    await page.keyboard.press("Enter");
    await expect(title).toBeFocused();
    await expect(title).toBeInViewport();
    await expect(page).toHaveURL(/\/dashboard$/);
  });

  test("pressed before the card is there, still goes to it once it's shown (#612)", async ({
    authedPage: page,
  }) => {
    await pressedBeforeTheCard(page, link(page), page.getByRole("heading", { name: "Bitcoin prices" }));
  });
});

test.describe("a choice to confirm after an update: the price card's link", () => {
  test.use({ priceSource: "unconfirmed" });

  test("pressed before the card is there, still goes to it once it's shown (#612)", async ({
    authedPage: page,
  }) => {
    await pressedBeforeTheCard(
      page,
      page.getByRole("link", { name: "Confirm now" }),
      page.getByRole("heading", { name: "Please confirm where BitcoinTX gets prices" }),
    );
  });
});
