import { describe, expect, it } from "vitest";
import { passwordTooShort } from "./credentials";

describe("passwordTooShort", () => {
  it("wants 12 characters", () => {
    expect(passwordTooShort("elevenchars")).toBe(true);
    expect(passwordTooShort("twelve-chars")).toBe(false);
  });

  it("counts code points, as the server does (#405)", () => {
    const key = "\u{1F511}"; // one code point, two UTF-16 units
    expect(passwordTooShort(key.repeat(6))).toBe(true);
    expect(passwordTooShort(key.repeat(12))).toBe(false);
    expect(Array.from("e\u0301").length).toBe(2); // a combining mark is a code point of its own, as in Python
  });
});
