import { describe, expect, it } from "vitest";
import { macSetupCodeHint, passwordTooShort, setupCodeHint } from "./credentials";
import { macApp } from "./prereleaseVersion";

describe("passwordTooShort", () => {
  it("wants 12 characters", () => {
    expect(passwordTooShort("elevenchars")).toBe(true);
    expect(passwordTooShort("twelve-chars")).toBe(false);
  });

  it("counts code points, as the server does (#405)", () => {
    const key = "\u{1F511}"; // one code point, two UTF-16 units
    expect(passwordTooShort(key.repeat(6))).toBe(true);
    expect(passwordTooShort(key.repeat(12))).toBe(false);
    expect(passwordTooShort("e\u0301".repeat(6))).toBe(false); // 12 code points, as Python's len(), in 6 letters
  });
});

describe("the Mac app's setup code hint", () => {
  it("names BitcoinTX Preview's own folder for a 2.0 alpha or beta (B10a)", () => {
    expect(macApp("2.0.0-beta.3")).toBe("BitcoinTX Preview");
    expect(macApp("2.0.0-alpha.1")).toBe("BitcoinTX Preview");
    expect(macApp("2.0.0")).toBe("BitcoinTX");
    expect(macApp("1.2.10")).toBe("BitcoinTX");
    expect(macApp("2.0.0-rc.1")).toBe("BitcoinTX");
  });

  it("names the Preview's folder for an alpha or a beta, BitcoinTX's otherwise", () => {
    expect(macSetupCodeHint("2.0.0-alpha.1")).toBe(
      "It is saved as setup-code.txt in BitcoinTX Preview's data folder (~/Library/Application Support/BitcoinTX Preview).");
    expect(macSetupCodeHint("2.0.0-beta.2")).toContain("(~/Library/Application Support/BitcoinTX Preview).");
    expect(macSetupCodeHint("1.2.10")).toBe(
      "It is saved as setup-code.txt in BitcoinTX's data folder (~/Library/Application Support/BitcoinTX).");
  });

  it("is this build's own folder", () => {
    const app = macApp(__BTCTX_VERSION__);
    expect(setupCodeHint(true)).toContain(`(~/Library/Application Support/${app}).`);
    expect(setupCodeHint(false)).not.toContain("Application Support");
  });
});
