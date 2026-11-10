// A guard on the click-through specs (#930): a route handler that asks the
// network itself, through route.fetch() or a request context, fails once its
// test's page is closed ("route.fetch: Test ended."), and Playwright reports
// that against whichever test runs next. So a spec with such a handler drops
// its routes after each test, from the page or context it routed. A handler
// that only waits, then continues or fulfills, is safe: those calls do
// nothing on a closed page. A shared helper can't drop routes for the tests
// that call it, so the helpers have no such handler at all. The specs are
// read as TypeScript reads them, so no comment, string or regex misleads it.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const e2eDir = fileURLToPath(new URL("../e2e", import.meta.url));
// A request context's own calls (page.request.get(…), the test's `request` fixture's)
const REQUEST_CALLS = new Set(["get", "post", "put", "patch", "delete", "head", "fetch"]);

/** `node` and every node under it. */
function subtree(node: ts.Node): ts.Node[] {
  const all: ts.Node[] = [];
  const visit = (n: ts.Node) => {
    all.push(n);
    ts.forEachChild(n, visit);
  };
  visit(node);
  return all;
}

/** The file's own functions by name: `function f() {}` and `const f = () => …`. */
function localFunctions(file: ts.SourceFile): Map<string, ts.Node> {
  const found = new Map<string, ts.Node>();
  for (const n of subtree(file)) {
    if (ts.isFunctionDeclaration(n) && n.name) found.set(n.name.text, n);
    else if (ts.isVariableDeclaration(n) && ts.isIdentifier(n.name) && n.initializer
      && (ts.isArrowFunction(n.initializer) || ts.isFunctionExpression(n.initializer))) found.set(n.name.text, n.initializer);
  }
  return found;
}

/** Whether `n` fetches through a route or a request context, never route.request(). */
function fetches(n: ts.Node): boolean {
  if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression)) {
    const { expression: target, name } = n.expression;
    if (name.text === "fetch") return true; // route.fetch(), whatever the handler calls its route
    if (ts.isIdentifier(target) && target.text === "request" && REQUEST_CALLS.has(name.text)) return true;
  }
  // page.request, or a context's, used or handed on; route.request() is the request routed
  return ts.isPropertyAccessExpression(n) && n.name.text === "request"
    && !(ts.isCallExpression(n.parent) && n.parent.expression === n);
}

/** Whether a handler asks the network, in its own code or a function of the file it calls. */
function asks(handler: ts.Node, locals: Map<string, ts.Node>, seen = new Set<ts.Node>()): boolean {
  seen.add(handler);
  return subtree(handler).some((n) => {
    if (fetches(n)) return true;
    const called = ts.isCallExpression(n) && ts.isIdentifier(n.expression) ? locals.get(n.expression.text) : undefined;
    return called !== undefined && !seen.has(called) && asks(called, locals, seen);
  });
}

/** Whether `.route(…)`'s handler asks: one not written in the file can't be read, so it counts. */
function handlerAsks(call: ts.CallExpression, locals: Map<string, ts.Node>): boolean {
  const handler = call.arguments[1];
  if (handler && (ts.isArrowFunction(handler) || ts.isFunctionExpression(handler))) return asks(handler, locals);
  const named = handler && ts.isIdentifier(handler) ? locals.get(handler.text) : undefined;
  return named === undefined || asks(named, locals);
}

/** What a route is on: the page, its context (`page.context()`, the `context` fixture), or another. */
function routerOf(target: ts.Expression): string {
  const text = target.getText();
  return text === "page.context()" ? "context" : text;
}

/** Whatever routes a handler that asks the network itself: "page", "context"… */
export function fetchingRouters(spec: string): Set<string> {
  const file = ts.createSourceFile("spec.ts", spec, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  const locals = localFunctions(file);
  const routers = new Set<string>();
  for (const n of subtree(file)) {
    if (ts.isCallExpression(n) && ts.isPropertyAccessExpression(n.expression) && n.expression.name.text === "route"
      && handlerAsks(n, locals)) routers.add(routerOf(n.expression.expression));
  }
  return routers;
}

/** Whether `call` is `<router>.unrouteAll({ behavior: "ignoreErrors" })`. */
function unroutesIgnoringErrors(call: ts.Node, router: string): boolean {
  if (!ts.isCallExpression(call) || !ts.isPropertyAccessExpression(call.expression)) return false;
  const { expression: target, name } = call.expression;
  const options = call.arguments[0];
  return name.text === "unrouteAll" && ts.isIdentifier(target) && target.text === router
    && options !== undefined && ts.isObjectLiteralExpression(options)
    && options.properties.some((p) => ts.isPropertyAssignment(p) && p.name.getText() === "behavior"
      && ts.isStringLiteral(p.initializer) && p.initializer.text === "ignoreErrors");
}

/** Whether the spec drops `router`'s routes, in flight or not, after each of its tests. */
export function dropsRoutesAfterEach(spec: string, router: string): boolean {
  const file = ts.createSourceFile("spec.ts", spec, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
  // At the top level: an afterEach inside a describe covers only that block
  return file.statements.some((s) => {
    if (!ts.isExpressionStatement(s) || !ts.isCallExpression(s.expression)) return false;
    const hook = s.expression;
    return hook.expression.getText() === "test.afterEach" && subtree(hook).some((n) => unroutesIgnoringErrors(n, router));
  });
}

/** What keeps a spec (or a helper) from dropping the routes that ask the network, in words. */
export function routeProblems(name: string, text: string, isSpec: boolean): string[] {
  return [...fetchingRouters(text)].flatMap((router) => {
    if (!isSpec) return [`${name}: a shared helper's handler on ${router} asks the network; move it into the spec`];
    if (router !== "page" && router !== "context") {
      return [`${name}: a handler on ${router} asks the network; only the page's or the context's routes are dropped after each test`];
    }
    return dropsRoutesAfterEach(text, router) ? []
      : [`${name}: ${router}'s handler asks the network; add a top-level test.afterEach awaiting ${router}.unrouteAll({ behavior: "ignoreErrors" })`];
  });
}

describe("a route handler that asks the network itself", () => {
  it.each([
    `await page.route("**/api/x", async (route) => { const real = await (await route.fetch()).json(); await route.fulfill({ json: real }); });`,
    `await page.route("**/api/x", async (route) => route.fulfill({ json: await (await page.request.get("/api/y")).json() }));`,
    `await page.route("**/api/x", async (r) => r.fulfill({ response: await r.fetch() }));`,
    `await page.route ("**/api/x", async (route) => route.fulfill({ response: await route.fetch() }));`,
    `test("t", async ({ page, request }) => {\n  await page.route("**/api/x", async (route) => route.fulfill({ json: await (await request.get("/api/y")).json() }));\n});`,
    `await page.route("**/api/x", relay);`,
    `async function relay(route: Route) { await route.fulfill({ response: await route.fetch() }); }\nawait page.route((url) => url.pathname === "/api/x", relay);`,
    `const relay = async (route: Route) => route.fulfill({ response: await route.fetch() });\nawait page.route("**/api/x", (route) => relay(route));`,
    // A glob's "/*" and "*/" aren't a comment (review of #930)
    `await page.route("**/api/bitcoin/**", async (route) => { const real = await (await route.fetch()).json(); await route.fulfill({ json: real }); });\n/** A helper. */\nfunction helper() {}`,
    `await page.route("**/api/x", async (route) => { /* :) don't */ const a = await route.fetch(); await route.fulfill({ response: a }); });`,
    `await page.route("**/api/x", async (route) => route.fulfill({ body: "a // b", headers: (await route.fetch()).headers() }));`,
  ])("is found in %s", (spec) => {
    expect(fetchingRouters(spec)).toEqual(new Set(["page"]));
  });

  it.each([
    [`await context.route("**/api/x", async (route) => { const a = await route.fetch(); held.push(() => route.fulfill({ response: a })); });`, "context"],
    [`await page.context().route("**", async (r) => r.fulfill({ response: await r.fetch() }));`, "context"],
    [`await pages[0].route("**", async (r) => r.fulfill({ response: await r.fetch() }));`, "pages[0]"],
  ])("is found on whatever it routes: %s", (spec, router) => {
    expect(fetchingRouters(spec)).toEqual(new Set([router]));
  });

  it.each([
    `await page.route("**/api/x", async (route) => { await held; await route.continue(); });`,
    `await page.route("**/api/x", (route) => route.request().method() === "GET" ? route.fulfill({ status: 500 }) : route.continue());`,
    `await page.route("**/api/x", async (route) => { const request = route.request(); if (request.method() === "POST") await wait(800); await route.continue(); });`,
    `// await page.route("**/api/x", async (route) => route.fulfill({ response: await route.fetch() }));`,
    `/*\n await page.route("**/api/x", async (route) => route.fulfill({ response: await route.fetch() }));\n*/`,
    `go(); /* page.route("**/api/x", async (route) => route.fulfill({ response: await route.fetch() })); */`,
    `await page.route("**/api/x", (route) => route.continue());\nconst real = await page.request.get("/api/y");`,
    `await expect(page.getByText(/kept in backups\\//)).toBeVisible();\nawait page.route("**/api/x", (route) => route.fulfill({ status: 502 }));`,
  ])("isn't found in %s", (spec) => {
    expect(fetchingRouters(spec).size).toBe(0);
  });

  it("is let through by a top-level afterEach that drops the same router's routes, ignoring their errors", () => {
    const pageAfterEach = `test.afterEach(async ({ page }) => {\n  // why\n  await page.unrouteAll({ behavior: "ignoreErrors" });\n});`;
    expect(dropsRoutesAfterEach(pageAfterEach, "page")).toBe(true);
    expect(dropsRoutesAfterEach(`test.afterEach(({ page }) => page.unrouteAll({ behavior: "ignoreErrors", }));`, "page")).toBe(true);
    expect(dropsRoutesAfterEach(`test.afterEach(async ({ page }) => { note(); await page.unrouteAll({ behavior: "ignoreErrors" }); });`, "page")).toBe(true);
    expect(dropsRoutesAfterEach(`test.afterEach(async ({ context }) => { await context.unrouteAll({ behavior: "ignoreErrors" }); });`, "context")).toBe(true);
    expect(dropsRoutesAfterEach(pageAfterEach, "context")).toBe(false); // the page's routes only
    expect(dropsRoutesAfterEach(`await page.unrouteAll({ behavior: "ignoreErrors" });`, "page")).toBe(false);
    expect(dropsRoutesAfterEach(`test.afterEach(async ({ page }) => { await page.unrouteAll(); });`, "page")).toBe(false);
    expect(dropsRoutesAfterEach(`test.describe("d", () => {\n  ${pageAfterEach}\n});`, "page")).toBe(false);
  });

  it("says what to do", () => {
    const spec = `await page.route("**/api/x", async (route) => route.fulfill({ response: await route.fetch() }));`;
    expect(routeProblems("a.e2e.ts", spec, true)).toEqual([
      `a.e2e.ts: page's handler asks the network; add a top-level test.afterEach awaiting page.unrouteAll({ behavior: "ignoreErrors" })`,
    ]);
    expect(routeProblems("fixtures.ts", spec, false)).toEqual([
      "fixtures.ts: a shared helper's handler on page asks the network; move it into the spec",
    ]);
    expect(routeProblems("b.e2e.ts", spec.replace("page.route", "second.route"), true)).toEqual([
      "b.e2e.ts: a handler on second asks the network; only the page's or the context's routes are dropped after each test",
    ]);
  });
});

describe("the click-through tests", () => {
  const files = readdirSync(e2eDir).filter((f) => f.endsWith(".ts"));

  it("are read, and their helpers", () => {
    expect(files).toContain("price-card.e2e.ts");
    expect(files).toContain("fixtures.ts");
  });

  it("drop their routes after each test wherever a handler asks the network, and their helpers have none (#930)", () => {
    const problems = files.flatMap((f) => routeProblems(f, readFileSync(join(e2eDir, f), "utf8"), f.endsWith(".e2e.ts")));
    expect(problems).toEqual([]);
  });

  it("find the handlers that do: #188's and holdLivePrices'", () => {
    const routers = (f: string) => fetchingRouters(readFileSync(join(e2eDir, f), "utf8"));
    expect(files.filter((f) => routers(f).size > 0).sort()).toEqual(["price-card.e2e.ts", "sidebar-matrix.e2e.ts"]);
  });
});
