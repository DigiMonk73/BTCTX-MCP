// @vitest-environment jsdom
// The banner on every page of a 2.0 pre-release, and BitcoinTX Preview's line
// on its first page (#670). The build's own version decides: on `2.0` an
// alpha or a beta, at 2.0.0 none, so these hold for either.
import "../test/setup";
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import api from "../api";
import { macApp, prereleaseBanner, previewFirstPageLine } from "../utils/prereleaseVersion";
import ChooseOwnLogin from "./ChooseOwnLogin";
import PrereleaseBanner from "./PrereleaseBanner";
import PrereleaseNotice from "./PrereleaseNotice";

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
  it("shows at once, then the Mac's words once the server says it is the Mac app", async () => {
    let answer: (value: unknown) => void = () => undefined;
    const get = vi.spyOn(api, "get").mockReturnValue(new Promise((ok) => (answer = ok)));
    render(<PrereleaseBanner />);
    const before = prereleaseBanner(__BTCTX_VERSION__, undefined);
    const after = prereleaseBanner(__BTCTX_VERSION__, true);
    if (!before || !after) {
      expect(banner()).toBeNull();
      expect(get).not.toHaveBeenCalled();
      return;
    }
    expect(screen.getByRole("note").textContent).toBe(`${before.title}: ${before.note}`);
    expect(get).toHaveBeenCalledWith("/users/setup-status");
    answer({ data: { desktop: true } });
    await waitFor(() => expect(screen.getByRole("note").textContent).toBe(`${after.title}: ${after.note}`));
  });

  it("keeps a server's words when the server doesn't answer: never the Mac's", async () => {
    vi.spyOn(api, "get").mockRejectedValue(new Error("offline"));
    render(<PrereleaseBanner />);
    const expected = prereleaseBanner(__BTCTX_VERSION__, undefined);
    await new Promise((ok) => setTimeout(ok, 0));
    if (expected) expect(screen.getByRole("note").textContent).toBe(`${expected.title}: ${expected.note}`);
    else expect(banner()).toBeNull();
  });
});

describe("ChooseOwnLogin", () => {
  const mount = () =>
    render(<ChooseOwnLogin windowApi={{} as PyWebViewAPI} onDone={async () => undefined} onNoCode={() => undefined} />);

  it("on BitcoinTX Preview's first page, says it starts empty and BitcoinTX is still there", () => {
    mount();
    const line = previewFirstPageLine(__BTCTX_VERSION__);
    if (line) expect(screen.getByText(line).tagName).toBe("P");
    else expect(screen.queryByText(/separate test app/)).toBeNull();
  });

  it("says which app still has the default login: the Preview, never the tester's BitcoinTX", () => {
    const { container } = mount();
    expect(container.textContent).toContain(`${macApp(__BTCTX_VERSION__)} still has the login it comes with (admin / password)`);
  });
});
