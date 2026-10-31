// The lint against comparing an account id with 1, 2, 3 or 4 (2.0 spec 5.4,
// 5.16; #356): an account is asked of the book, never by its number. External
// (99) and the fee accounts (5, 6) stay fixed ids everywhere.
import { fileURLToPath } from "node:url";
import { ESLint } from "eslint";
import { describe, expect, it } from "vitest";

const eslint = new ESLint({ cwd: fileURLToPath(new URL("..", import.meta.url)) });
const RULE = "no-restricted-syntax";

async function refusals(code: string, filePath = "src/utils/example.ts"): Promise<number> {
  const [result] = await eslint.lintText(`${code}\n`, { filePath });
  return result.messages.filter((m) => m.ruleId === RULE).length;
}

describe("the lint against an account id compared with 1 to 4", () => {
  it.each([
    "export const a = (tx: { from_account_id: number }) => tx.from_account_id === 2;",
    "export const b = (id: number) => 4 === id;",
    "export const c = (toAccountId: number) => toAccountId !== 3;",
    "export const d = (accountId: number) => accountId == 1;",
    "export const e = (account: { id: number }) => account.id === 4;",
    "export function f(account_id: number) { switch (account_id) { case 1: return 'Bank'; default: return ''; } }",
    "export const g = (from_account_id: number) => [1, 3].includes(from_account_id);",
    "export const h = (tx: { to_account_id: number }) => [2, 4].indexOf(tx.to_account_id) >= 0;",
  ])("refuses %s", async (code) => {
    expect(await refusals(code)).toBe(1);
  });

  it("refuses it in a component too", async () => {
    expect(await refusals("export const g = (to_account_id: number) => to_account_id === 2;", "src/components/X.tsx"))
      .toBe(1);
  });

  it.each([
    "export const a = (fee_currency: string) => fee_currency === 'BTC';",
    "export const b = (to_account_id: number) => to_account_id === 99;",
    "export const c = (from_account_id: number) => from_account_id === 5;",
    "export const d = (n: number) => n === 1;",
    "export const e = (rows: number[]) => rows.length === 1;",
    "export const f = (valid: number) => valid === 2;",
    "export function g(count: number) { switch (count) { case 1: return 'one'; default: return ''; } }",
    "export const h = (n: number) => [1, 2].includes(n);",
    // A named constant, defined once with why (B7b's FIRST_OF_EACH mirrors services/account.FIRST_OF_EACH)
    "const FIRST_OF_EACH = new Set([1, 2, 3, 4]);\nexport const i = (id: number) => FIRST_OF_EACH.has(id);",
  ])("leaves %s alone", async (code) => {
    expect(await refusals(code)).toBe(0);
  });

  it("leaves the tests alone: their books are numbered", async () => {
    expect(await refusals("export const a = (account_id: number) => account_id === 2;", "src/utils/x.test.ts"))
      .toBe(0);
  });
});
