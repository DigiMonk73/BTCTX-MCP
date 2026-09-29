// The Mac app renders with the system WebKit: Safari 15 on macOS 10.15.
// Safari before 15.4 doesn't know :focus-visible, and drops any rule whose
// selector list contains one; keyboard focus must still show there.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const dir = join(__dirname);
const rules = readdirSync(dir)
  .filter((f) => f.endsWith(".css"))
  .flatMap((f) => {
    const css = readFileSync(join(dir, f), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");
    return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
      file: f,
      selectors: m[1].trim().split(",").map((s) => s.trim()),
      body: m[2],
    }));
  });

describe("focus styles in Safari 15", () => {
  it("no selector list mixes :focus-visible with selectors old WebKit understands", () => {
    // VM test 2026-09-29 (F10): ".input:focus, .input:focus-visible" was dropped whole.
    const mixed = rules.filter(
      (r) => r.selectors.length > 1 && r.selectors.some((s) => s.includes(":focus-visible")),
    );
    expect(mixed.map((r) => `${r.file}: ${r.selectors.join(", ")}`)).toEqual([]);
  });

  it("the focus outline is only removed where something else shows focus", () => {
    // VM test 2026-09-29 (F10): "*:focus { outline: none }" with the ring on
    // *:focus-visible left no focus ring at all before Safari 15.4. A rule
    // that draws its own focus (border or shadow) may drop the outline.
    const removed = rules.filter(
      (r) =>
        /outline\s*:\s*(none|0)\b/.test(r.body) &&
        !/box-shadow|border-color/.test(r.body) &&
        r.selectors.some((s) => /:focus(?!-visible|-within)/.test(s) && !s.includes(":not(:focus-visible)")),
    );
    expect(removed.map((r) => `${r.file}: ${r.selectors.join(", ")}`)).toEqual([]);
  });
});
