// B6a-10: a guard on the transaction form's source (spec 5.4, D7). The form knows an
// account only by its id, through the book (accounts.ts): never by a 1.x kind, a
// fixed number or a nickname, which the owner can change. Each B6a step deleted what
// it made dead, so this passes from B6a-8 on; it fails a later change that brings one
// back, until B8-6's lint covers the whole frontend.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const src = join(__dirname, "..");
const formDir = join(src, "components", "transactionForm");

/** The form's own files, its tests left out (they name ids on purpose). */
const FORM_FILES = [
  join(src, "utils", "transactionForm.ts"),
  join(src, "utils", "transferAmounts.ts"),
  join(src, "utils", "accounts.ts"),
  join(src, "utils", "useAccounts.ts"),
  join(src, "components", "TransactionForm.tsx"),
  ...readdirSync(formDir)
    .filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f))
    .map((f) => join(formDir, f)),
];

/** Code without its comments, so a "why" that names 1.x's kinds doesn't count. */
function code(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:"'`])\/\/.*$/gm, "$1");
}

// 1.x's kinds and the functions that mapped them to fixed ids
const OLD_NAMES = /\b(AccountType|buyFromAccount|mapAccountToId|accountIdToType)\b/;

// Something that holds an account id: an account, an id, a payer, the picker's choice
const HOLDS_ID = String.raw`[\w.?]*(?:[Aa]ccount\w*|[Ii]d|_id|[Pp]ayer\w*|chosen)`;
const FIXED_ID = String.raw`[1-4](?![\d.])`;
const EQ = String.raw`\s*[!=]==?\s*`;
// The 1.x ids (Bank 1, Wallet 2, Exchange USD 3, Exchange BTC 4); External's 99 is allowed
const FIXED_ID_COMPARED = new RegExp(`\\b${HOLDS_ID}${EQ}${FIXED_ID}|\\b${FIXED_ID}${EQ}${HOLDS_ID}\\b`);

// A nickname compared with a literal, either way round
const NAME_COMPARED = new RegExp(
  String.raw`\.name${EQ}["'\x60]|["'\x60]${EQ}[\w.?]*\.name\b|\b(?:accountName|exchangeName)\([^)]*\)${EQ}["'\x60]`,
);

const RULES: [string, RegExp][] = [
  ["a 1.x account kind", OLD_NAMES],
  ["an account id compared with 1, 2, 3 or 4", FIXED_ID_COMPARED],
  ["an account's nickname compared with a literal", NAME_COMPARED],
];

/** Every line of `text` a rule refuses, as "file:line: why". */
function offences(file: string, text: string): string[] {
  return code(text)
    .split("\n")
    .flatMap((line, i) =>
      RULES.filter(([, rule]) => rule.test(line)).map(([why]) => `${file}:${i + 1}: ${why}`),
    );
}

describe("the transaction form knows accounts only by id", () => {
  it("scans every form file", () => {
    expect(FORM_FILES.length).toBeGreaterThan(10);
  });

  it("names no 1.x kind, compares no id with a 1.x number and no nickname with a literal", () => {
    const found = FORM_FILES.flatMap((file) =>
      offences(file.slice(src.length + 1), readFileSync(file, "utf8")),
    );
    expect(found).toEqual([]);
  });
});

describe("the scan itself", () => {
  it.each([
    "if (data.fromAccountId === 4) {",
    "const bank = tx.to_account_id !== 1;",
    "return 3 == payerId;",
    "if (chosen === 2) return;",
    "account.name === \"Wallet\"",
    "'Exchange BTC' !== account?.name",
    "accountName(book, id) === `Bank`",
    "data.buyFromAccount",
    "function f(kind: AccountType) {}",
  ])("refuses %s", (line) => {
    expect(offences("x.ts", line)).not.toEqual([]);
  });

  it.each([
    "options.length === 1 && chosen === options[0]",
    "id === EXTERNAL_ID",
    "data.toAccountId === 99",
    "amount === 1.5",
    "const fee = from - to; // a move from 2 to 4 (1.x) ",
    "/* account === 4 */ ok()",
    "account.name",
  ])("allows %s", (line) => {
    expect(offences("x.ts", line)).toEqual([]);
  });
});
