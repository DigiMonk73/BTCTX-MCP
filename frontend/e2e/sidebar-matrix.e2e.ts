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
  test, expect, outsideRequests, claimAccount, loginViaUi, choosePriceSource, fakePastPrice, CURRENT_PRICE,
  PRICE_CHOICE_SAVED, type PriceChoice,
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

type Price = number | "not chosen yet" | "offline" | "no answer" | "No price";

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

/**
 * The hourly history's download: Bitstamp's hourly candles in its fixed
 * blocks of 1,000 hours from each 1 January 00:00 UTC (services/price_files.py).
 * Not the backup's lookup of newer hours, which starts the hour after the
 * history ends (review of #186).
 */
function historyDownload(r: OutsideRequest): boolean {
  const url = new URL(r.url);
  if (!r.url.startsWith("https://www.bitstamp.net/api/v2/ohlc/btcusd/") || url.searchParams.get("step") !== "3600") {
    return false;
  }
  // A history ending exactly on a block's edge would let the backup's first newer block
  // through too: true of no manifest yet (the open year ends mid-block)
  const start = Number(url.searchParams.get("start"));
  const yearStart = Date.UTC(new Date(start * 1000).getUTCFullYear(), 0, 1) / 1000;
  return (start - yearStart) % (1000 * 3600) === 0;
}
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

/** What Auto says besides the price (#208): where it came from, or whether Tor is running. */
type Says = { from?: string; torDown?: boolean };

async function useAuto(sidebar: Locator, live: Price, says: Says) {
  await expect(sidebar.getByRole("button", { name: "Auto" })).toHaveAttribute("aria-pressed", "true");
  await expect(sidebar.getByText(`BTC Price: ${shown(live)}`, { exact: true })).toBeVisible();
  await expect(sidebar).not.toContainText("$0.00");
  // "Kraken · 2:04 pm": the site, or your Mempool, and the time it answered
  const from = sidebar.getByText(/ · \d{1,2}:\d\d [ap]m$/);
  if (says.from) await expect(from).toHaveText(new RegExp(`^${says.from} · \\d{1,2}:\\d\\d [ap]m$`));
  else await expect(from).toHaveCount(0);
  await expect(sidebar.getByText("Is Tor running?", { exact: true })).toHaveCount(says.torDown ? 1 : 0);
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
async function useEveryMode(page: Page, live: Price, day: Price, says: Says = {}) {
  const sidebar = page.getByRole("complementary");
  const display = sidebar.getByRole("status", { name: "Calculator display" });
  // From the sidebar's top: the page scrolls to whatever is clicked.
  const edges = async () => {
    const top = (await sidebar.boundingBox())!.y;
    const box = (await display.locator("xpath=..").boundingBox())!;
    return [Math.round(box.y - top), Math.round(box.y + box.height - top)];
  };
  await press(sidebar, "12+");
  await useAuto(sidebar, live, says);
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
async function answerTheFirstRunQuestion(
  page: Page, app: App, answer: (prompt: Locator) => Promise<void>, from: string,
) {
  const browser = await logIn(page, app);
  await useEveryMode(page, "not chosen yet", "No price");
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
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE, { from });
  return sentOut(app, browser);
}

test("not chosen yet: nothing is asked and Manual works; picking public sites brings the prices", async ({
  page, app,
}) => {
  const sent = await answerTheFirstRunQuestion(
    page, app, (prompt) => prompt.getByLabel(/^Public price sites/).check(), "Kraken",
  );
  expect(proxies(sent)).toEqual([null]);
});

test("off: nothing is asked; Auto and Date say so, Manual works", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choosePriceSource(page, { price_source: "off" });
  await useEveryMode(page, "offline", "No price");
  expect(sentOut(app, browser)).toEqual([]);
});

test("public sites: the prices, asked directly", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choosePriceSource(page, { price_source: "public" });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE, { from: "Kraken" });
  expect(proxies(sentOut(app, browser))).toEqual([null]);
});

test("public sites through Tor: the prices, every request through the proxy", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choosePriceSource(page, { price_source: "public", proxy_url: TOR });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE, { from: "Kraken, through Tor" });
  expect(proxies(sentOut(app, browser))).toEqual([TOR]);
});

test("public sites with Tor stopped: no price, asks whether Tor is running; nothing goes around the proxy", async ({
  page, app,
}) => {
  const browser = await logIn(page, app);
  await choosePriceSource(page, { price_source: "public", proxy_url: TOR_STOPPED });
  await useEveryMode(page, "no answer", "No price", { torDown: true });
  expect(proxies(sentOut(app, browser))).toEqual([TOR_STOPPED]);
});

test("own mempool server: the prices, from it alone", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choosePriceSource(page, { price_source: "mempool", mempool_url: MEMPOOL });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE, { from: "Your Mempool" });
  expect(origins(sentOut(app, browser))).toEqual([MEMPOOL]);
});

test("own mempool server down, no backup: no price, and no public site is asked", async ({ page, app }) => {
  const browser = await logIn(page, app);
  await choosePriceSource(page, { price_source: "mempool", mempool_url: MEMPOOL_DOWN });
  await useEveryMode(page, "no answer", "No price");
  expect(origins(sentOut(app, browser))).toEqual([MEMPOOL_DOWN]);
});

test("own mempool server with the public backup: the backup isn't asked while it answers", async ({
  page, app,
}) => {
  const browser = await logIn(page, app);
  await choosePriceSource(page, { price_source: "mempool", mempool_url: MEMPOOL, mempool_fallback: true });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE, { from: "Your Mempool" });
  // Besides your Mempool, only the hourly history's one-time download, which the
  // backup starts when saved (#145): Bitstamp's fixed hourly blocks, no date in them
  const sent = sentOut(app, browser);
  expect(origins(sent.filter((r) => !historyDownload(r)))).toEqual([MEMPOOL]);
});

test("own mempool server down, with the public backup: the prices from the public sites", async ({
  page, app,
}) => {
  const browser = await logIn(page, app);
  await choosePriceSource(page, { price_source: "mempool", mempool_url: MEMPOOL_DOWN, mempool_fallback: true });
  await useEveryMode(page, CURRENT_PRICE, DAY_PRICE, { from: "Kraken" }); // the backup answered
  const sent = sentOut(app, browser).filter((r) => !historyDownload(r));
  expect(origins(sent)[0]).toBe(MEMPOOL_DOWN); // asked first
  expect(origins(sent).length).toBeGreaterThan(1); // then the public sites
  expect(proxies(sent)).toEqual([null]);
});

/**
 * The live price's answers, each fetched at once (with the choice of that
 * moment) but handed to the page only when released: an answer for the old
 * choice can then arrive after the new one.
 */
async function holdLivePrices(page: Page) {
  const held: (() => Promise<void>)[] = [];
  const state = { holding: true };
  await page.route("**/api/bitcoin/price", async (route) => {
    if (!state.holding) return route.continue();
    const answer = await route.fetch();
    held.push(() => route.fulfill({ response: answer }));
  });
  return { held, state };
}

/**
 * Save a choice and send the card's event at once, as choosePriceSource does
 * but without waiting for the sidebar's answer first: one may be on its way.
 */
async function saveInPlace(page: Page, choice: PriceChoice) {
  const r = await page.request.put("/api/settings/network", {
    data: { mempool_url: null, mempool_fallback: false, proxy_url: null, ...choice },
  });
  expect(r.ok(), await r.text()).toBeTruthy();
  await page.evaluate((event) => window.dispatchEvent(new Event(event)), PRICE_CHOICE_SAVED);
}

test("saved in place: an answer for the old choice arriving last is dropped (#327)", async ({ page, app }) => {
  const live = await holdLivePrices(page);
  await logIn(page, app);
  await expect.poll(() => live.held.length).toBe(2); // the sidebar's and the Dashboard's, not chosen yet
  await saveInPlace(page, { price_source: "public" });
  await expect.poll(() => live.held.length).toBe(4);
  const sidebar = page.getByRole("complementary");
  for (const send of live.held.slice(2)) await send(); // the new choice's answers first
  await expect(sidebar.getByText(`BTC Price: ${dollars(CURRENT_PRICE)}`, { exact: true })).toBeVisible();
  for (const send of live.held.slice(0, 2)) await send(); // then the old ones, late
  await page.waitForTimeout(500); // nothing more to wait on: they've been handed over
  await expect(sidebar.getByText(`BTC Price: ${dollars(CURRENT_PRICE)}`, { exact: true })).toBeVisible();
  await expect(sidebar.getByText(/^Kraken · \d{1,2}:\d\d [ap]m$/)).toBeVisible();
});

test("saved in place: the old price never shows the new choice's source (review of #319)", async ({ page, app }) => {
  await logIn(page, app);
  await choosePriceSource(page, { price_source: "public" });
  const sidebar = page.getByRole("complementary");
  await expect(sidebar.getByText(/^Kraken · \d{1,2}:\d\d [ap]m$/)).toBeVisible();
  const live = await holdLivePrices(page);
  await saveInPlace(page, { price_source: "public", proxy_url: TOR });
  await expect.poll(() => live.held.length).toBe(2);
  // Until the answer through Tor comes: "…", and no source line on the direct price
  await expect(sidebar.getByText("BTC Price: …", { exact: true })).toBeVisible();
  await expect(sidebar.getByText(/ · \d{1,2}:\d\d [ap]m$/)).toHaveCount(0);
  live.state.holding = false;
  for (const send of live.held) await send();
  await expect(sidebar.getByText(/^Kraken, through Tor · \d{1,2}:\d\d [ap]m$/)).toBeVisible();
});

test("Date with an hour: that hour on this device's clock, its UTC day's price here; nothing names the day", async ({
  page, app,
}) => {
  // #145: 23:00 in Chicago is 05:00 UTC the next day; 05:00 in Tokyo, 20:00 UTC the day before.
  // The fake internet has day prices only, so the hour's price is its UTC day's.
  const browser = await logIn(page, app);
  // Tax timezone UTC, unlike this device's (#260): an hour read in the tax timezone
  // would show the picked UTC day's price, not the device hour's.
  const tz = await page.request.put("/api/settings/tax-timezone", { data: { timezone: "UTC", chosen: true } });
  expect(tz.ok(), await tz.text()).toBeTruthy();
  await choosePriceSource(page, { price_source: "public" });
  const sidebar = page.getByRole("complementary");
  await sidebar.getByRole("button", { name: "Date" }).click();
  await sidebar.getByLabel("Select date").fill(DAY);
  await expect(sidebar.getByText(shown(DAY_PRICE), { exact: true })).toBeVisible(); // the day, as before
  const tokyo = (await page.evaluate(() => Intl.DateTimeFormat().resolvedOptions().timeZone)) === "Asia/Tokyo";
  await sidebar.getByLabel("Hour").selectOption(tokyo ? "5" : "23");
  const expected = fakePastPrice(tokyo ? "2024-02-29" : "2024-03-02");
  await expect(sidebar.getByText(shown(expected), { exact: true })).toBeVisible();
  // #555: and the line under the date and hour names that day, not the date picked
  await expect(sidebar.getByText(`Day's price: ${tokyo ? "Feb 29" : "Mar 2"}, 00:00 UTC`, { exact: true })).toBeVisible();
  sentOut(app, browser); // no request named the day, or the hour
});

test.describe("set by the server (StartOS)", () => {
  test.use({ priceSource: "startos" });

  test("the prices from its Mempool alone", async ({ page, app }) => {
    const browser = await logIn(page, app);
    await useEveryMode(page, CURRENT_PRICE, DAY_PRICE, { from: "Your Mempool" });
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
    }, "Your Mempool");
    expect(origins(sent)).toEqual([MEMPOOL]);
  });

  test("off: nothing is asked; Auto and Date say so, Manual works", async ({ page, app }) => {
    const browser = await logIn(page, app);
    await choosePriceSource(page, { price_source: "off" });
    await useEveryMode(page, "offline", "No price");
    expect(sentOut(app, browser)).toEqual([]);
  });
});
