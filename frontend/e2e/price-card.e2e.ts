// The price card (#145): the first-run question on the Dashboard and
// Settings › Privacy & network. Keyboard only, the status line in the
// redesign's words for each state (with a fake internet, so the app's own
// price code runs), and the sizes it must fit: the Mac app's 800 × 600 and
// a phone. The browser asks nobody but BitcoinTX throughout.
import { test, expect, claimAccount, loginViaUi, outsideRequests, type App } from "./fixtures";
import type { Page } from "@playwright/test";

test.use({ fakeInternet: true, priceSource: "unset" });

const MEMPOOL_DOWN = "http://mempool.invalid:3006"; // the fake internet never answers .invalid
const TOR_STOPPED = "socks5h://tor.invalid:9050";

async function logIn(page: Page, app: App): Promise<string[]> {
  const outside: string[] = [];
  page.on("request", (req) => {
    if (!req.url().startsWith(app.url) && !req.url().startsWith("data:")) outside.push(req.url());
  });
  await claimAccount(page.request, app);
  await loginViaUi(page);
  return outside;
}

async function choose(page: Page, data: Record<string, unknown>) {
  const r = await page.request.put("/api/settings/network", {
    data: { mempool_url: null, mempool_fallback: false, proxy_url: null, ...data },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
}

/** The card's status line in Settings, once the Dashboard has asked for a price. */
async function statusAfterAPrice(page: Page) {
  await page.goto("/dashboard"); // asks for the live price with the choice just saved
  await expect(page.locator(".btc-price-value")).toHaveText(/^(\$|Error)/);
  await page.getByRole("link", { name: "Settings" }).click();
  return page.getByRole("region", { name: "Privacy & network" }).getByRole("status");
}

test("keyboard only: Tab into the choices, the arrows pick, Tab to the button, Enter saves", async ({
  page, app, browserName,
}) => {
  // Safari's Tab skips radios and tick boxes unless the Mac's "Keyboard navigation" is on
  test.skip(browserName === "webkit", "Safari tabs to text fields only by default");
  const browser = await logIn(page, app);
  const card = page.getByRole("region", { name: "Bitcoin prices" });
  await card.getByLabel(/^My own Mempool/).focus();
  await page.keyboard.press("ArrowDown"); // to Public price sites
  await expect(card.getByLabel(/^Public price sites/)).toBeChecked();
  await expect(card.getByLabel(/^Public price sites/)).toBeFocused();
  await page.keyboard.press("Tab"); // its own field comes right after it
  await expect(card.getByLabel("Through Tor")).toBeFocused();
  await page.keyboard.press("Space");
  await expect(card.getByLabel("Tor's address")).toBeVisible();
  await page.keyboard.press("Space"); // and back off
  await expect(card.getByLabel("Tor's address")).toHaveCount(0);
  await page.keyboard.press("Tab"); // past Nobody, a radio of the same group, to the button
  await expect(card.getByRole("button", { name: "Use this" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(card).toHaveCount(0);
  expect((await (await page.request.get("/api/settings/network")).json()).price_source).toBe("public");
  expect(browser).toEqual([]);
});

test("your Mempool down, with the backup: the status says the public sites answered instead", async ({ page, app }) => {
  await logIn(page, app);
  await choose(page, { price_source: "mempool", mempool_url: MEMPOOL_DOWN, mempool_fallback: true });
  const status = await statusAfterAPrice(page);
  await expect(status).toHaveText(/Your Mempool didn't answer at \d+:\d\d [ap]m\. Public price sites answered instead at/);
  await expect(status).not.toContainText("from your Mempool");
});

test("your Mempool down, no backup: the status says so and what to do; no public site is asked", async ({
  page, app,
}) => {
  await logIn(page, app);
  await choose(page, { price_source: "mempool", mempool_url: MEMPOOL_DOWN });
  const status = await statusAfterAPrice(page);
  await expect(status).toContainText("Your Mempool didn't answer at");
  await expect(status).toContainText("If it can't answer, ask public price sites");
  expect([...new Set(outsideRequests(app).map((r) => new URL(r.url).origin))]).toEqual([MEMPOOL_DOWN]);
});

test("public sites through a stopped Tor: the status asks whether Tor is running", async ({ page, app }) => {
  await logIn(page, app);
  await choose(page, { price_source: "public", proxy_url: TOR_STOPPED });
  const status = await statusAfterAPrice(page);
  await expect(status).toHaveText(/Public price sites didn't answer through Tor at .*Is Tor running\?/);
});

test("public sites answering: the status names them and the time", async ({ page, app }) => {
  await logIn(page, app);
  await choose(page, { price_source: "public" });
  const status = await statusAfterAPrice(page);
  await expect(status).toHaveText(/Newer prices from public price sites\. Last price \d+:\d\d [ap]m\./);
});

test.describe("the Mac app's window, 800 × 600", () => {
  test.use({ appMode: "mac", viewport: { width: 800, height: 600 } });

  test("the first-run card fits: no sideways scrolling, and its button shows", async ({ page, app }) => {
    await logIn(page, app);
    const card = page.getByRole("region", { name: "Bitcoin prices" });
    await expect(card.getByRole("button", { name: "Use this" })).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});

test.describe("a phone", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("the card stacks without sideways scrolling, each choice at least 44px tall", async ({ page, app }) => {
    await logIn(page, app);
    const card = page.getByRole("region", { name: "Bitcoin prices" });
    await card.getByLabel(/^My own Mempool/).check();
    await card.getByLabel("If it can't answer, ask public price sites").check();
    await card.getByLabel("Through Tor").check();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    for (const row of await card.locator(".price-choice").all()) {
      expect((await row.boundingBox())!.height).toBeGreaterThanOrEqual(44);
    }
  });
});
