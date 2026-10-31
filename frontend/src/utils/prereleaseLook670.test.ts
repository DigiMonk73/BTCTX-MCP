// A 2.0 pre-release says so on every page, and BitcoinTX Preview's first page
// says its empty ledger isn't BitcoinTX's (#670): BitcoinTX Preview, the Mac
// app of the alphas and betas, looked like BitcoinTX itself.
import { describe, expect, it } from "vitest";
import { prereleaseBanner, previewFirstPageLine } from "./prereleaseVersion";

const text = (banner: ReturnType<typeof prereleaseBanner>) => banner && `${banner.title}: ${banner.note}`;

describe("prereleaseBanner", () => {
  it("on a Mac, is BitcoinTX Preview, apart from your BitcoinTX", () => {
    expect(text(prereleaseBanner("2.0.0-alpha.2", true)))
      .toBe("BitcoinTX Preview · 2.0.0-alpha.2: a test version, apart from your BitcoinTX");
    expect(text(prereleaseBanner("2.0.0-beta.3", true)))
      .toBe("BitcoinTX Preview · 2.0.0-beta.3: a test version, apart from your BitcoinTX");
  });

  it("on a server, is BitcoinTX itself, updated in place or on its own volume: nothing of apart", () => {
    expect(text(prereleaseBanner("2.0.0-alpha.2", false))).toBe("BitcoinTX · 2.0.0-alpha.2: a test version, not a release");
  });

  it("before the server says which, says what is true on every install, a server's words", () => {
    expect(text(prereleaseBanner("2.0.0-beta.1", undefined))).toBe("BitcoinTX · 2.0.0-beta.1: a test version, not a release");
  });

  it("is none for a release, or a version it can't read", () => {
    for (const version of ["2.0.0", "1.2.10", "2.0.0-rc.1", "2.0.0-alpha.0", "dev", undefined]) {
      for (const desktop of [true, false, undefined]) expect(prereleaseBanner(version, desktop)).toBeNull();
    }
  });
});

describe("previewFirstPageLine", () => {
  it("tells a tester the Preview starts empty and their BitcoinTX is still there", () => {
    expect(previewFirstPageLine("2.0.0-alpha.2")).toBe(
      "BitcoinTX Preview is a separate test app: it starts empty, and BitcoinTX and its ledger are still there, as they were.",
    );
    expect(previewFirstPageLine("2.0.0-beta.1")).toBe(previewFirstPageLine("2.0.0-alpha.2"));
  });

  it("is none for BitcoinTX itself", () => {
    for (const version of ["2.0.0", "1.2.10", undefined]) expect(previewFirstPageLine(version)).toBeNull();
  });
});
