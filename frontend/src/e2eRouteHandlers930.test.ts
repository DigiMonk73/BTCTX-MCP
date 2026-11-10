// A guard on the click-through specs (#930): a route handler that asks the
// network itself, through route.fetch() or a request context, fails once its
// test's page is closed ("route.fetch: Test ended."), and Playwright reports
// that against whichever test runs next. So a spec with such a handler drops
// its routes before each test ends. A handler that only waits, then continues
// or fulfills, is safe: those calls do nothing on a closed page.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const e2eDir = fileURLToPath(new URL("../e2e", import.meta.url));

/** Code without its comments, so a "why" that names route.fetch() doesn't count. */
function code(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

/** The text from an opening bracket to its match, skipping what's quoted. */
function bracketed(text: string, open: number): string {
  let depth = 0;
  for (let i = open; i < text.length; i++) {
    const c = text[i];
    if (c === '"' || c === "'" || c === "`") {
      i = text.indexOf(c, i + 1);
      if (i < 0) break;
    } else if (c === "(") depth++;
    else if (c === ")" && --depth === 0) return text.slice(open, i + 1);
  }
  return text.slice(open);
}

// route.fetch(), or a request context's call (page.request.get(…)), never route.request()
const ASKS_THE_NETWORK = /\broute\.fetch\(|\.request\b(?!\s*\()/;
const DROPS_ROUTES = /test\.afterEach\([^)]*\)\s*=>\s*\{?\s*(?:await\s+)?page\.unrouteAll\(\{\s*behavior:\s*["']ignoreErrors["']\s*\}\)/;

/** Whether one of the spec's route handlers asks the network itself. */
export function hasFetchingHandler(spec: string): boolean {
  const text = code(spec);
  for (const m of text.matchAll(/\.route\(/g)) {
    if (ASKS_THE_NETWORK.test(bracketed(text, m.index + m[0].length - 1))) return true;
  }
  return false;
}

/** Whether the spec drops its routes, in flight or not, before each test ends. */
export function dropsRoutesAfterEach(spec: string): boolean {
  return DROPS_ROUTES.test(code(spec));
}

describe("a route handler that asks the network itself", () => {
  it.each([
    `await page.route("**/api/x", async (route) => { const real = await (await route.fetch()).json(); await route.fulfill({ json: real }); });`,
    `await page.route("**/api/x", async (route) => route.fulfill({ json: await (await page.request.get("/api/y")).json() }));`,
    `await context.route("**/api/x", async (route) => { const a = await route.fetch(); held.push(() => route.fulfill({ response: a })); });`,
  ])("is found in %s", (spec) => {
    expect(hasFetchingHandler(spec)).toBe(true);
  });

  it.each([
    `await page.route("**/api/x", async (route) => { await held; await route.continue(); });`,
    `await page.route("**/api/x", (route) => route.request().method() === "GET" ? route.fulfill({ status: 500 }) : route.continue());`,
    `// await page.route("**/api/x", async (route) => route.fulfill({ response: await route.fetch() }));`,
    `await page.route("**/api/x", (route) => route.continue());\nconst real = await page.request.get("/api/y");`,
  ])("isn't found in %s", (spec) => {
    expect(hasFetchingHandler(spec)).toBe(false);
  });

  it("is let through by an afterEach that drops the routes, ignoring their errors", () => {
    expect(dropsRoutesAfterEach(`test.afterEach(async ({ page }) => {\n  await page.unrouteAll({ behavior: "ignoreErrors" });\n});`)).toBe(true);
    expect(dropsRoutesAfterEach(`test.afterEach(({ page }) => page.unrouteAll({ behavior: "ignoreErrors" }));`)).toBe(true);
    expect(dropsRoutesAfterEach(`await page.unrouteAll({ behavior: "ignoreErrors" });`)).toBe(false);
    expect(dropsRoutesAfterEach(`test.afterEach(async ({ page }) => { await page.unrouteAll(); });`)).toBe(false);
  });
});

describe("the click-through specs", () => {
  const specs = readdirSync(e2eDir).filter((f) => f.endsWith(".e2e.ts"));

  it("are read", () => {
    expect(specs).toContain("price-card.e2e.ts");
  });

  it.fails("drop their routes after each test wherever a handler asks the network (#930)", () => {
    const left = specs.filter((f) => {
      const spec = readFileSync(join(e2eDir, f), "utf8");
      return hasFetchingHandler(spec) && !dropsRoutesAfterEach(spec);
    });
    expect(left).toEqual([]);
  });
});
