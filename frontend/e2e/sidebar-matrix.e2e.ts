// The sidebar's converter and calculator under every price source (#147).
// In each state, Auto shows the live price or a plain message (never $0.00),
// Date shows that day's stored price or a plain message, Manual works from a
// typed price, and the calculator works throughout. The prices come from a
// fake internet (fixtures: fakeInternet), so the app's own choice of source,
// fallback and proxy runs, and what it sends out is checked too: nothing
// before a choice or while off, only to the chosen source, and nothing that
// names the day. The browser itself asks nobody but BitcoinTX, from its
// first request on.
import {
  test, expect, outsideRequests, claimAccount, loginViaUi, fakePastPrice, CURRENT_PRICE,
  type App, type OutsideRequest,
} from "./fixtures";
import type { Locator, Page } from "@playwright/test";

// A fresh install, so every outside request belongs to the state a test chooses.
test.use({ fakeInternet: true, priceSource: "unset" });

// The day Date mode looks up: not the first day of a block the public price
// history comes in (1,000 days each from 2011-08-18), which requests do name.
const DAY = "2024-03-01";
// $50,083.00: each day has its own price, so a lookup of the wrong day shows.
const DAY_PRICE = fakePastPrice(DAY);
const MEMPOOL = "http://umbrel.local:3006";
const TOR = "socks5h://127.0.0.1:9050";
// The fake internet never answers a host under .invalid: a server that's down.
const MEMPOOL_DOWN = "http://mempool.invalid:3006";
const TOR_STOPPED = "socks5h://tor.invalid:9050";
const STARTOS_MEMPOOL = "http://10.0.3.1:32768"; // fixtures: priceSource "startos"

type Price = number | "Prices off" | "No price";
type Network = {
  price_source: "off" | "public" | "mempool";
  mempool_url?: string;
  mempool_fallback?: boolean;
  proxy_url?: string;
};

/** Every request the browser makes from now on to anywhere but BitcoinTX. */
function watchBrowser(page: Page, app: App): string[] {
  const outside: string[] = [];
  page.on("request", (req) => {
    const url = req.url();
    if (!url.startsWith(app.url) && !url.startsWith("data:") && !url.startsWith("blob:")) outside.push(url);
  });
  return outside;
}

/** Claim the fresh install and log in, watching the browser from its first request. */
async function logIn(page: Page, app: App): Promise<string[]> {
  const browser = watchBrowser(page, app);
  await claimAccount(page.request, app);
  await loginViaUi(page);
  return browser;
}

/** Save a price source as Settings → Privacy & network does, then load the page again. */
async function choose(page: Page, network: Network) {
  const r = await page.request.put("/api/settings/network", {
    data: { mempool_url: null, mempool_fallback: false, proxy_url: null, ...network },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
  await page.reload();
}

const DAY_SECONDS = 86_400;
const MIDNIGHT = Date.parse(`${DAY}T00:00:00Z`) / 1000;

/**
 * Whether a URL names DAY: as a date (it or a day either side, with or
 * without dashes), or as any moment from the day before to the day after,
 * as a 10- or 13-digit Unix time in seconds or milliseconds (a local
 * midnight anywhere, noon, a window around the day). No honest request
 * comes near: the public history's blocks start 1,000 days apart.
 */
function namesTheDay(url: string): boolean {
  const text = decodeURIComponent(url);
  const days = [-1, 0, 1].map((n) => new Date((MIDNIGHT + n * DAY_SECONDS) * 1000).toISOString().slice(0, 10));
  const dates = days.flatMap((d) => [d, d.replaceAll("-", "")]);
  const times = (text.match(/\d+/g) ?? []).filter((n) => n.length === 10 || n.length === 13);
  return dates.some((d) => new RegExp(`(^|\\D)${d}(\\D|$)`).test(text))
    || times.some((n) => {
      const seconds = Number(n) / (n.length === 13 ? 1000 : 1);
      return seconds >= MIDNIGHT - DAY_SECONDS && seconds < MIDNIGHT + 2 * DAY_SECONDS;
    });
}

/**
 * What the server sent out, once it's checked that none of it named the day
 * and that the browser asked nobody but BitcoinTX.
 */
function sentOut(app: App, browser: string[]): OutsideRequest[] {
  expect(browser).toEqual([]);
  const sent = outsideRequests(app);
  expect(sent.filter((r) => namesTheDay(r.url))).toEqual([]);
  return sent;
}

/** The hourly history's download: Bitstamp's hourly candles in fixed blocks (services/price_files.py). */
const historyDownload = (r: OutsideRequest) =>
  r.url.startsWith("https://www.bitstamp.net/api/v2/ohlc/btcusd/") && new URL(r.url).searchParams.get("step") === "3600";
const origins = (sent: OutsideRequest[]) => [...new Set(sent.map((r) => new URL(r.url).origin))];
const proxies = (sent: OutsideRequest[]) => [...new Set(sent.map((r) => r.proxy))];

const dollars = (n: number) =>
  "$" + n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const shown = (price: Price) => (typeof price === "number" ? dollars(price) : price);
const field = (sidebar: Locator, name: string) => sidebar.getByLabel(name, { exact: true });

async function press(sidebar: Locator, keys: string) {
  for (const k of keys) await sidebar.getByRole("button", { name: k, exact: true }).click();
}

/** Type a BTC amount: the sats always follow, the USD only with a price. */
async function convertBtc(sidebar: Locator, btc: number, price: Price) {
  await field(sidebar, "BTC").fill(String(btc));
  await expect(field(sidebar, "Sats")).toHaveValue(String(btc * 100_000_000));
  await expect(field(sidebar, "USD")).toHaveValue(typeof price === "number" ? String(btc * price) : "");
}

async function useAuto(sidebar: Locator, live: Price) {
  await expect(sidebar.getByRole("button", { name: "Auto" })).toHaveAttribute("aria-pressed", "true");
  await expect(sidebar.getByText(`BTC Price: ${shown(live)}`, { exact: true })).toBeVisible();
  await expect(sidebar).not.toContainText("$0.00");
  await convertBtc(sidebar, 0.5, live);
}

async function useDate(sidebar: Locator, day: Price) {
  await sidebar.getByRole("button", { name: "Date" }).click();
  await sidebar.getByLabel("Select date").fill(DAY);
  await expect(sidebar.getByText(shown(day), { exact: true })).toBeVisible();
  await expect(sidebar).not.toContainText("$0.00");
  await convertBtc(sidebar, 1, day);
}

async function useManual(sidebar: Locator, live: Price) {
  await sidebar.getByRole("button", { name: "Manual" }).click();
  const price = sidebar.getByLabel("BTC price (USD)");
  // It starts from the live price when there is one, never from a made-up one.
  await expect(price).toHaveValue(typeof live === "number" ? String(live) : /^0?$/);
  await price.fill("80000");
  await field(sidebar, "USD").fill("400");
  await expect(field(sidebar, "BTC")).toHaveValue("0.005");
  await expect(field(sidebar, "Sats")).toHaveValue("500000");
  await price.fill("100000"); // a new price converts the typed USD again
  await expect(field(sidebar, "BTC")).toHaveValue("0.004");
  await expect(field(sidebar, "Sats")).toHaveValue("400000");
}

/**
 * Use the sidebar as the owner would: Auto, Date and Manual, with a
 * calculation running across the mode switches. The calculator stays put
 * whichever mode's row shows (owner's request, 2026-09-29).
 */
async function useEveryMode(page: Page, live: Price, day: Price) {
  const sidebar = page.getByRole("complementary");
  const display = sidebar.getByRole("status", { name: "Calculator display" });
  // From the sidebar's top: the page scrolls to whatever is clicked.
  const edges = async () => {
    const top = (await sidebar.boundingBox())!.y;
    const box = (await display.locator("xpath=..").boundingBox())!;
    return [Math.round(box.y - top), Math.round(box.y + box.height - top)];
  };
  await press(sidebar, "12+");
  await useAuto(sidebar, live);
  const inAuto = await edges();
  await useDate(sidebar, day);
  expect(await edges()).toEqual(inAuto);
  await press(sidebar, "30=");
  await expect(display).toHaveText("42");
  await useManual(sidebar, live);
  expect(await edges()).toEqual(inAuto);
  await press(sidebar, "C7*6=");
  await expect(display).toHaveText("42");
}

/**
 * A fresh install's sidebar before the first-run question is answered (no
 * prices, nothing asked), then after `answer` picks a source in it. Returns
 * what the server sent out.
 */
async function answerTheFirstRunQuestion(page: Page, app: App, answer: (prompt: Locator) => Promise<void>) {
  const browser = await logIn(page, app);
  await useEveryMode(page, "Prices off", "No price");
  expect(sentOut(app, browser)).toEqual([]);

  const prompt = page.getByRole("region", { name: "Bitcoin prices" });
  await answer(prompt);
  // Saved in place: the sidebar asks again, with no page load (#145, #149)
  await prompt.getByRole("button", { name: "Use this" }).click();
  await expect(prompt).toHaveCount(0);
  // The sidebar stays as it was (in Manual, the calculator showing 42): back to Auto, cleared
  const sidebar = page.getByRole("complementary");
  await sidebar.getByRole("button", { name: "Auto" }).click();
  await press(sidebar, "C");
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE);
  return sentOut(app, browser);
}

test("not chosen yet: nothing is asked and Manual works; picking public sites brings the prices", async ({
  page, app,
}) => {
  const sent = await answerTheFirstRunQuestion(page, app, (prompt) => prompt.getByLabel(/^Public price sites/).check());
  expect(proxies(sent)).toEqual([null]);
});

test("off: nothing is asked; Auto and Date say so, Manual works", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choose(page, { price_source: "off" });
  await useEveryMode(page, "Prices off", "No price");
  expect(sentOut(app, browser)).toEqual([]);
});

test("public sites: the prices, asked directly", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choose(page, { price_source: "public" });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE);
  expect(proxies(sentOut(app, browser))).toEqual([null]);
});

test("public sites through Tor: the prices, every request through the proxy", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choose(page, { price_source: "public", proxy_url: TOR });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE);
  expect(proxies(sentOut(app, browser))).toEqual([TOR]);
});

test("public sites with Tor stopped: no price, and nothing goes around the proxy", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choose(page, { price_source: "public", proxy_url: TOR_STOPPED });
  await useEveryMode(page, "No price", "No price");
  expect(proxies(sentOut(app, browser))).toEqual([TOR_STOPPED]);
});

test("own mempool server: the prices, from it alone", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choose(page, { price_source: "mempool", mempool_url: MEMPOOL });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE);
  expect(origins(sentOut(app, browser))).toEqual([MEMPOOL]);
});

test("own mempool server down, no backup: no price, and no public site is asked", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choose(page, { price_source: "mempool", mempool_url: MEMPOOL_DOWN });
  await useEveryMode(page, "No price", "No price");
  expect(origins(sentOut(app, browser))).toEqual([MEMPOOL_DOWN]);
});

test("own mempool server with the public backup: the backup isn't asked while it answers", async ({
  page, app,
}) => {
  const browser = await logIn(page, app);
  await choose(page, { price_source: "mempool", mempool_url: MEMPOOL, mempool_fallback: true });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE);
  // Besides your Mempool, only the hourly history's one-time download, which the
  // backup starts when saved (#145): Bitstamp's fixed hourly blocks, no date in them
  const sent = sentOut(app, browser);
  expect(origins(sent.filter((r) => !historyDownload(r)))).toEqual([MEMPOOL]);
});

test("own mempool server down, with the public backup: the prices from the public sites", async ({
  page, app,
}) => {
  const browser = await logIn(page, app);
  await choose(page, { price_source: "mempool", mempool_url: MEMPOOL_DOWN, mempool_fallback: true });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE);
  const sent = sentOut(app, browser).filter((r) => !historyDownload(r));
  expect(origins(sent)[0]).toBe(MEMPOOL_DOWN); // asked first
  expect(origins(sent).length).toBeGreaterThan(1); // then the public sites
  expect(proxies(sent)).toEqual([null]);
});

test.describe("set by the server (StartOS)", () => {
  test.use({ priceSource: "startos" });

  test("the prices from its Mempool alone", async ({ page, app }) => {
    const browser = await logIn(page, app);
    await useEveryMode(page, CURRENT_PRICE, DAY_PRICE);
    expect(origins(sentOut(app, browser))).toEqual([STARTOS_MEMPOOL]);
  });
});

test.describe("the Mac app", () => {
  test.use({ appMode: "mac" });

  test("not chosen yet: nothing is asked; picking the own mempool server brings the prices", async ({
    page, app,
  }) => {
    const sent = await answerTheFirstRunQuestion(page, app, async (prompt) => {
      await prompt.getByLabel(/^My own Mempool/).check();
      await prompt.getByLabel("Your Mempool's address").fill(MEMPOOL);
    });
    expect(origins(sent)).toEqual([MEMPOOL]);
  });

  test("off: nothing is asked; Auto and Date say so, Manual works", async ({ page, app }) => {
    const browser = await logIn(page, app);
    await choose(page, { price_source: "off" });
    await useEveryMode(page, "Prices off", "No price");
    expect(sentOut(app, browser)).toEqual([]);
  });
});
