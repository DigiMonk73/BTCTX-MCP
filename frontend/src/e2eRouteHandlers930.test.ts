// A guard on the click-through specs (#930): a route handler that asks the
// network itself, through route.fetch() or a request context, fails once its
// test's page is closed ("route.fetch: Test ended."), and Playwright reports
// that against whichever test runs next. So a spec with such a handler drops
// its routes after each test, from the page or context it routed. A handler
// that only waits, then continues or fulfills, is safe: those calls do
// nothing on a closed page. A shared helper can't drop routes for the tests
// that call it, so the helpers have no such handler at all.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const e2eDir = fileURLToPath(new URL("../e2e", import.meta.url));

/**
 * Code without its comments, so a "why" that names route.fetch() doesn't
 * count. A block comment is taken only where it starts a line: a glob such
 * as "**\/api/bitcoin/**" holds both a block comment's opening and its end.
 */
function code(text: string): string {
  return text.replace(/^[ \t]*\/\*[\s\S]*?\*\//gm, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
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

// A fetch through the route or a request context (page.request.get(…), the test's
// own `request`), whatever the handler calls its route; never route.request()
const ASKS_THE_NETWORK = /\.fetch\(|\.request\b(?!\s*\()|\brequest\.(?:get|post|put|patch|delete|head|fetch)\s*\(/;
// A handler passed by name can't be read here: it counts as one that asks
const INLINE_HANDLER = /=>|\bfunction\b/;

/** Whatever routes a handler that asks the network itself: "page", "context"… */
export function fetchingRouters(spec: string): Set<string> {
  const text = code(spec);
  const routers = new Set<string>();
  for (const m of text.matchAll(/(\w+)\s*\.route\s*\(/g)) {
    const args = bracketed(text, m.index + m[0].length - 1);
    if (ASKS_THE_NETWORK.test(args) || !INLINE_HANDLER.test(args)) routers.add(m[1]);
  }
  return routers;
}

/** Whether the spec drops `router`'s routes, in flight or not, after each of its tests. */
export function dropsRoutesAfterEach(spec: string, router: string): boolean {
  // At the top level: an afterEach inside a describe covers only that block
  const drops = new RegExp(
    String.raw`^test\.afterEach\([^)]*\b${router}\b[^)]*\)\s*=>\s*\{?\s*(?:await\s+)?${router}\.unrouteAll\(\{\s*behavior:\s*["']ignoreErrors["']\s*\}\)`,
    "m",
  );
  return drops.test(code(spec));
}

describe("a route handler that asks the network itself", () => {
  it.each([
    `await page.route("**/api/x", async (route) => { const real = await (await route.fetch()).json(); await route.fulfill({ json: real }); });`,
    `await page.route("**/api/x", async (route) => route.fulfill({ json: await (await page.request.get("/api/y")).json() }));`,
    `await page.route("**/api/x", async (r) => r.fulfill({ response: await r.fetch() }));`,
    `await page.route ("**/api/x", async (route) => route.fulfill({ response: await route.fetch() }));`,
    `test("t", async ({ page, request }) => {\n  await page.route("**/api/x", async (route) => route.fulfill({ json: await (await request.get("/api/y")).json() }));\n});`,
    `await page.route("**/api/x", relay);`,
    // A glob's "/*" and "*/" aren't a comment, so the handler between them is read (review of #930)
    `await page.route("**/api/bitcoin/**", async (route) => { const real = await (await route.fetch()).json(); await route.fulfill({ json: real }); });\n/** A helper. */\nfunction helper() {}`,
  ])("is found in %s", (spec) => {
    expect(fetchingRouters(spec)).toEqual(new Set(["page"]));
  });

  it("is found on a context too, as the context's", () => {
    const spec = `await context.route("**/api/x", async (route) => { const a = await route.fetch(); held.push(() => route.fulfill({ response: a })); });`;
    expect(fetchingRouters(spec)).toEqual(new Set(["context"]));
  });

  it.each([
    `await page.route("**/api/x", async (route) => { await held; await route.continue(); });`,
    `await page.route("**/api/x", (route) => route.request().method() === "GET" ? route.fulfill({ status: 500 }) : route.continue());`,
    `// await page.route("**/api/x", async (route) => route.fulfill({ response: await route.fetch() }));`,
    `/*\n await page.route("**/api/x", async (route) => route.fulfill({ response: await route.fetch() }));\n*/`,
    `await page.route("**/api/x", (route) => route.continue());\nconst real = await page.request.get("/api/y");`,
    `await page.route("**/api/bitcoin/**", (route) => route.fulfill({ status: 502 }));\n/** A helper. */\nconst real = await (await page.request.get("/api/y")).json();`,
  ])("isn't found in %s", (spec) => {
    expect(fetchingRouters(spec).size).toBe(0);
  });

  it("is let through by a top-level afterEach that drops the same router's routes, ignoring their errors", () => {
    const pageAfterEach = `test.afterEach(async ({ page }) => {\n  // why\n  await page.unrouteAll({ behavior: "ignoreErrors" });\n});`;
    expect(dropsRoutesAfterEach(pageAfterEach, "page")).toBe(true);
    expect(dropsRoutesAfterEach(`test.afterEach(({ page }) => page.unrouteAll({ behavior: "ignoreErrors" }));`, "page")).toBe(true);
    expect(dropsRoutesAfterEach(`test.afterEach(async ({ context }) => { await context.unrouteAll({ behavior: "ignoreErrors" }); });`, "context")).toBe(true);
    expect(dropsRoutesAfterEach(pageAfterEach, "context")).toBe(false); // the page's routes only
    expect(dropsRoutesAfterEach(`await page.unrouteAll({ behavior: "ignoreErrors" });`, "page")).toBe(false);
    expect(dropsRoutesAfterEach(`test.afterEach(async ({ page }) => { await page.unrouteAll(); });`, "page")).toBe(false);
    expect(dropsRoutesAfterEach(`test.describe("d", () => {\n  ${pageAfterEach}\n});`, "page")).toBe(false);
  });
});

describe("the click-through tests", () => {
  const files = readdirSync(e2eDir).filter((f) => f.endsWith(".ts"));
  const specs = files.filter((f) => f.endsWith(".e2e.ts"));
  const read = (f: string) => readFileSync(join(e2eDir, f), "utf8");

  it("are read, and their helpers", () => {
    expect(specs).toContain("price-card.e2e.ts");
    expect(files).toContain("fixtures.ts");
  });

  it("drop their routes after each test wherever a handler asks the network (#930)", () => {
    const left = specs.flatMap((f) => {
      const spec = read(f);
      return [...fetchingRouters(spec)].filter((router) => !dropsRoutesAfterEach(spec, router)).map((router) => `${f}: ${router}`);
    });
    expect(left).toEqual([]);
  });

  it("have no such handler in a shared helper", () => {
    expect(files.filter((f) => !specs.includes(f) && fetchingRouters(read(f)).size > 0)).toEqual([]);
  });
});
