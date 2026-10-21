// B8-6 (spec 5.4; #356 item 5): the lint refuses an account id compared with
// 1, 2, 3 or 4, and an account's name compared with a text (Rick, 2026-10-20,
// question 11). Runs ESLint's API with the project's own config on snippets,
// each linted as a file under src/.
import { ESLint } from "eslint";
import path from "node:path";
import { describe, expect, it } from "vitest";

const NO_FIXED_ID = "An account is found by its id from the book (utils/accounts.ts), never by a fixed number (spec 5.4).";
const NO_NAME = "An account's name is the owner's nickname: show it, never compare it (Rick, 2026-10-20).";

const eslint = new ESLint({ cwd: path.resolve(__dirname, "..") });

/** The no-restricted-syntax messages ESLint gives `code`, linted as src/lintFixture.ts. */
async function refusals(code: string): Promise<string[]> {
  const [result] = await eslint.lintText(`export function check(tx: any, account: any, fromAccountId: number, amount: number) {\n${code}\n}\n`,
    { filePath: path.resolve(__dirname, "lintFixture.ts") });
  return result.messages.filter((m) => m.ruleId === "no-restricted-syntax").map((m) => m.message);
}

describe("an account id is never compared with 1, 2, 3 or 4 (5.4)", () => {
  it.each([
    "return tx.from_account_id === 2;",
    "return fromAccountId !== 4;",
    "return 1 == tx.to_account_id;",
    "return tx.accountId != 3;",
    "return account.id === 1;",
  ])("refuses %s", async (code) => {
    expect(await refusals(code)).toEqual([NO_FIXED_ID]);
  });

  it("refuses a case 3: in a switch on an account id", async () => {
    expect(await refusals("switch (tx.to_account_id) { case 3: return 1; default: return 0; }")).toEqual([NO_FIXED_ID]);
  });

  it("refuses 1.x's TransactionRow: a switch on id, and an id compared in a helper", async () => {
    const code = "const isUsd = (id: number) => id === 1 || id === 3;\n"
      + "switch (fromAccountId) { case 1: return isUsd(1); case 99: return 0; }";
    expect(await refusals(code)).toEqual([NO_FIXED_ID, NO_FIXED_ID, NO_FIXED_ID]);
  });

  it.each([
    "return tx.to_account_id === 99;",
    "return amount === 2;",
    "return tx.from_account_id === tx.to_account_id;",
    "return tx.from_account_id === 5;",
    "switch (amount) { case 3: return 1; default: return 0; }",
  ])("allows %s", async (code) => {
    expect(await refusals(code)).toEqual([]);
  });
});

describe("a nickname is never compared with a text (Rick, 2026-10-20)", () => {
  it.each([
    'return account.name === "Wallet";',
    "return 'Bank' !== account.name;",
  ])("refuses %s", async (code) => {
    expect(await refusals(code)).toEqual([NO_NAME]);
  });

  it.each([
    'return account.kind === "wallet";',
    "return account.name === tx.name;",
    "return account.name;",
  ])("allows %s", async (code) => {
    expect(await refusals(code)).toEqual([]);
  });
});

describe("the app's code keeps both rules", () => {
  it("lints the app's code in src/ clean of them (tests' fixtures name ids on purpose)", async () => {
    const results = await eslint.lintFiles(["src/**/*.{ts,tsx}"]);
    const found = results.flatMap((r) => r.messages
      .filter((m) => m.ruleId === "no-restricted-syntax")
      .map((m) => `${path.relative(path.resolve(__dirname, ".."), r.filePath)}:${m.line}`));
    expect(found).toEqual([]);
    // The rule is on: a snippet with a fixed id is refused (else an empty list proves nothing)
    expect(await refusals("return tx.from_account_id === 2;")).toHaveLength(1);
  }, 120_000);
});
