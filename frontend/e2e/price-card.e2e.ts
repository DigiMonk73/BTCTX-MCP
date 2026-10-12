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

test.describe("the Mac app's window, 800 × 600, after the update", () => {
  test.use({ appMode: "mac", viewport: { width: 800, height: 600 }, priceSource: "unconfirmed" });

  test("the confirm card fits too: its Confirm button shows", async ({ page, app }) => {
    await logIn(page, app);
    const card = page.getByRole("region", { name: "Please confirm where BitcoinTX gets prices" });
    await expect(card.getByRole("button", { name: "Confirm" })).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  });
});

test.describe("Tor on this server, set in StartOS (#145)", () => {
  test.use({ priceSource: "public", serverTor: true });

  test("Settings shows Through Tor ticked and locked, with no address to type", async ({ page, app }) => {
    await logIn(page, app);
    await page.getByRole("link", { name: "Settings" }).click();
    const net = page.getByRole("region", { name: "Privacy & network" });
    await expect(net.getByLabel("Through Tor")).toBeChecked();
    await expect(net.getByLabel("Through Tor")).toBeDisabled();
    await expect(net.getByText(/^Tor on this server, set in StartOS/)).toBeVisible();
    await expect(net.getByLabel("Tor's address")).toHaveCount(0);
    await net.getByLabel(/^Nobody/).check(); // the rest stays the owner's to change
    await net.getByRole("button", { name: "Save" }).click();
    const shown = await (await page.request.get("/api/settings/network")).json();
    expect([shown.price_source, shown.proxy_url, shown.tor_from_server]).toEqual(["off", "socks5h://10.0.3.1:9050", true]);
  });
});

test.describe("the Mac app's window, 800 × 600, a Mempool to confirm", () => {
  test.use({ appMode: "mac", viewport: { width: 800, height: 600 }, priceSource: "unconfirmed-mempool" });

  test("its Confirm button is reached by scrolling down, never sideways", async ({ page, app }) => {
    // A Mempool's address, backup and Tor fields make this one-time card taller than
    // the window (#186's review): a short scroll down, no sideways scrolling
    await logIn(page, app);
    const card = page.getByRole("region", { name: "Please confirm where BitcoinTX gets prices" });
    const confirm = card.getByRole("button", { name: "Confirm" });
    await confirm.scrollIntoViewIfNeeded();
    await expect(confirm).toBeInViewport();
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

test.describe("confirm once after the update (#145, 2.9)", () => {
  test.use({ priceSource: "unconfirmed" });

  test("a choice an older release stored is asked once, pre-selected; nothing is sent until Confirm", async ({
    page, app,
  }) => {
    const browser = await logIn(page, app);
    const card = page.getByRole("region", { name: "Please confirm where BitcoinTX gets prices" });
    await expect(card).toBeVisible();
    await expect(card.getByLabel(/^Public price sites/)).toBeChecked();
    await expect(card.locator(".price-choice.chosen")).toContainText("Public price sitesYour current choice");
    await expect(card.getByRole("status")).toHaveText(/Waiting for you to confirm: nothing is contacted until you do\./);
    await expect(page.locator(".btc-price-value")).toHaveText("Confirm your choice");
    await expect(page.getByRole("link", { name: "Confirm now" })).toBeVisible();
    await expect(page.getByRole("complementary")).toContainText("BTC Price: waiting for you · Confirm");
    await expect(page.getByRole("complementary").getByRole("link", { name: "Confirm" })).toBeVisible();
    await page.goto("/dashboard"); // after a restart of the page: still asked, still nothing sent
    await expect(card).toBeVisible();
    expect(outsideRequests(app)).toEqual([]);

    await card.getByRole("button", { name: "Confirm" }).click();
    await expect(card).toHaveCount(0);
    await expect(page.locator(".btc-price-value")).toHaveText(/^\$/); // asked now, in place
    expect(outsideRequests(app).length).toBeGreaterThan(0);
    const shown = await (await page.request.get("/api/settings/network")).json();
    expect([shown.price_source, shown.confirmed, shown.chosen_via]).toEqual(["public", true, "first-run"]);
    await page.goto("/dashboard");
    await expect(page.getByRole("region", { name: /Bitcoin prices|Please confirm/ })).toHaveCount(0);
    await page.getByRole("link", { name: "Settings" }).click();
    await expect(page.getByText(/^You chose this on .* at .*, in the first-run question\.$/)).toBeVisible();
    expect(browser).toEqual([]);
  });

  test("changing the choice while confirming saves the new one", async ({ page, app }) => {
    await logIn(page, app);
    const card = page.getByRole("region", { name: "Please confirm where BitcoinTX gets prices" });
    await card.getByLabel(/^Nobody/).check();
    await card.getByRole("button", { name: "Use this" }).click();
    await expect(card).toHaveCount(0);
    const shown = await (await page.request.get("/api/settings/network")).json();
    expect([shown.price_source, shown.confirmed]).toEqual(["off", true]);
    expect(outsideRequests(app)).toEqual([]);
  });
});

for (const [fixture, label] of [["unconfirmed-off", "Nobody"], ["unconfirmed-mempool", "My own Mempool"]] as const) {
  test.describe(`confirm once: ${label}`, () => {
    test.use({ priceSource: fixture });

    test("asked with it pre-selected; nothing is sent before Confirm, and only to the choice after", async ({
      page, app,
    }) => {
      await logIn(page, app);
      const card = page.getByRole("region", { name: "Please confirm where BitcoinTX gets prices" });
      await expect(card.locator(".price-choice.chosen")).toContainText(`${label}Your current choice`);
      await page.goto("/dashboard");
      await expect(card).toBeVisible();
      expect(outsideRequests(app)).toEqual([]);
      await card.getByRole("button", { name: "Confirm" }).click();
      await expect(card).toHaveCount(0);
      const origins = [...new Set(outsideRequests(app).map((r) => new URL(r.url).origin))];
      expect(origins).toEqual(fixture === "unconfirmed-off" ? [] : ["http://umbrel.local:3006"]);
    });
  });
}

test.describe("a server whose price settings aren't valid", () => {
  test.use({ priceSource: "invalid" });

  test("Settings says so, read-only, and nothing is asked", async ({ page, app }) => {
    const browser = await logIn(page, app);
    await expect(page.getByRole("region", { name: "Bitcoin prices" })).toHaveCount(0);
    await page.getByRole("link", { name: "Settings" }).click();
    const net = page.getByRole("region", { name: "Privacy & network" });
    await expect(net.getByText(/Set by this server's settings \(BTCTX_PRICE_SOURCE\)/)).toBeVisible();
    await expect(net.getByRole("status")).toHaveText(/This server's price settings aren't valid, so nothing is contacted\./);
    await expect(net.getByRole("radio")).toHaveCount(0);
    await expect(net.getByRole("button", { name: "Save" })).toHaveCount(0);
    expect(outsideRequests(app)).toEqual([]);
    expect(browser).toEqual([]);
  });
});
