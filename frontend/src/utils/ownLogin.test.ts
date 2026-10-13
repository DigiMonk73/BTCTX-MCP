import { describe, expect, it } from "vitest";
import { ownLoginProblem } from "./ownLogin";

const GOOD = "own-password-1";

describe("ownLoginProblem", () => {
  it("accepts a username and a 12-character password typed twice", () => {
    expect(ownLoginProblem("owner", GOOD, GOOD)).toBeNull();
    expect(ownLoginProblem("owner", "twelve-chars", "twelve-chars")).toBeNull();
  });

  it("asks for a username", () => {
    expect(ownLoginProblem("   ", GOOD, GOOD)).toBe("Enter a username.");
  });

  it("refuses admin, as Register does", () => {
    expect(ownLoginProblem(" Admin ", GOOD, GOOD)).toMatch(/^The username 'admin' is reserved/);
  });

  it("refuses a password under 12 characters", () => {
    expect(ownLoginProblem("owner", "elevenchars", "elevenchars")).toBe(
      "The new password is too short. At least 12 characters.",
    );
  });

  it("refuses two passwords that differ", () => {
    expect(ownLoginProblem("owner", GOOD, GOOD + " ")).toBe("The two passwords don't match.");
  });
});
