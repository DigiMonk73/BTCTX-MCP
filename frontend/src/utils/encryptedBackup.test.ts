import { describe, expect, it } from "vitest";
import { BACKUP_PASSWORD_HINT, backupPasswordProblem } from "./encryptedBackup";

describe("backupPasswordProblem", () => {
  it("accepts a 12-character password typed twice", () => {
    expect(backupPasswordProblem("twelve-chars", "twelve-chars")).toBeNull();
  });

  it("refuses a shorter one, the login passwords' rule (#204)", () => {
    expect(backupPasswordProblem("eleven-char", "eleven-char")).toBe(
      "The password is too short. At least 12 characters.",
    );
  });

  it("counts characters as the server does", () => {
    const sixEmoji = "\u{1F511}".repeat(6); // 12 UTF-16 units, 6 characters
    expect(backupPasswordProblem(sixEmoji, sixEmoji)).toMatch(/too short/);
  });

  it("refuses two passwords that differ", () => {
    expect(backupPasswordProblem("twelve-chars", "twelve-chars ")).toBe("The two passwords don't match.");
  });

  it("says older backups still restore", () => {
    expect(BACKUP_PASSWORD_HINT).toMatch(/^At least 12 characters\. .*shorter password still restores\.$/);
  });
});
