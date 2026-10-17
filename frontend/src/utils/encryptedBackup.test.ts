import { describe, expect, it } from "vitest";
import { BACKUP_PASSWORD_HINT, backupPasswordProblem, restoreOutcome } from "./encryptedBackup";

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

describe("restoreOutcome", () => {
  const RESTORED = "✅ Database successfully restored. Log in again with your current username and password.";

  it("moves on to the login page after an ordinary restore", () => {
    expect(restoreOutcome({ message: RESTORED })).toEqual({ message: RESTORED, waits: false });
  });

  it("waits for the owner to read a notice (#407)", () => {
    const notice = "The backup's tax timezone, 'localtime', isn't a timezone name BitcoinTX knows, ...";
    expect(restoreOutcome({ message: RESTORED, notice })).toEqual({ message: `${RESTORED} ${notice}`, waits: true });
  });
});
