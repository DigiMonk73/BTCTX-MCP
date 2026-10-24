// @vitest-environment jsdom
// The banner on every page of a 2.0 pre-release, and BitcoinTX Preview's line
// on its first page (#670). The build's own version decides: on `2.0` an
// alpha or a beta, at 2.0.0 none, so these hold for either.
import "../test/setup";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import { prereleaseBanner, previewFirstPageLine } from "../utils/prereleaseVersion";
import ChooseOwnLogin from "./ChooseOwnLogin";
import PrereleaseBanner, { PrereleaseNotice } from "./PrereleaseBanner";

const banner = () => document.querySelector(".prerelease-banner");

describe("PrereleaseNotice", () => {
  it("names the test version, as a note", () => {
    render(<PrereleaseNotice version="2.0.0-alpha.2" desktop />);
    expect(screen.getByRole("note").textContent).toBe(
      "BitcoinTX Preview · 2.0.0-alpha.2: a test version, apart from your BitcoinTX",
    );
  });

  it("shows nothing for a release", () => {
    render(<PrereleaseNotice version="2.0.0" desktop />);
    expect(banner()).toBeNull();
  });
});

describe("PrereleaseBanner", () => {
  it("asks the server whether it is the Mac app, then says this build's version", async () => {
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: { desktop: false } });
    render(<PrereleaseBanner />);
    const expected = prereleaseBanner(__BTCTX_VERSION__, false);
    if (expected) {
      expect((await screen.findByRole("note")).textContent).toBe(`${expected.title}: ${expected.note}`);
      expect(get).toHaveBeenCalledWith("/users/setup-status");
    } else {
      expect(banner()).toBeNull();
      expect(get).not.toHaveBeenCalled();
    }
  });

  it("claims nothing when the server doesn't answer", async () => {
    vi.spyOn(api, "get").mockRejectedValue(new Error("offline"));
    render(<PrereleaseBanner />);
    const expected = prereleaseBanner(__BTCTX_VERSION__, undefined);
    if (expected) expect((await screen.findByRole("note")).textContent).toBe(`${expected.title}: ${expected.note}`);
    else expect(banner()).toBeNull();
  });
});

describe("ChooseOwnLogin", () => {
  it("on BitcoinTX Preview's first page, says it starts empty and BitcoinTX is still there", () => {
    render(<ChooseOwnLogin windowApi={{} as PyWebViewAPI} onDone={async () => undefined} onNoCode={() => undefined} />);
    const line = previewFirstPageLine(__BTCTX_VERSION__);
    if (line) expect(screen.getByText(line).tagName).toBe("P");
    else expect(screen.queryByText(/separate test app/)).toBeNull();
  });
});
