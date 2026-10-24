// @vitest-environment jsdom
// Settings → Connect an AI Assistant's "Set up with an older version?" for a
// 2.0 pre-release (B10a, #532): the Preview's own server name and pin, and
// the bitcointx that reaches this BitcoinTX only on a server install
// (StartOS, updated in place). On a Mac, or while the install isn't known
// yet, that bitcointx is the installed app's, never to be changed.
import "../test/setup";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { OlderVersionHint } from "./ConnectAiSetting";

const text = (version: string | undefined, serverMode: boolean) =>
  render(<OlderVersionHint version={version} serverMode={serverMode} />).container.textContent ?? "";

describe("OlderVersionHint", () => {
  it("on a server install, names the Preview's server and the bitcointx that reaches this BitcoinTX", () => {
    const hint = text("2.0.0-alpha.1", true);
    expect(hint).toContain("for bitcointx-preview (or for the bitcointx that reaches this BitcoinTX) to btctx-mcp==2.0.0a1");
  });

  it("on a Mac, or before the install is known, names only the Preview's own server", () => {
    const hint = text("2.0.0-beta.2", false);
    expect(hint).toContain("for bitcointx-preview to btctx-mcp==2.0.0b2");
    expect(hint).not.toContain("(or for the bitcointx");
  });

  it("for a release, names bitcointx and its pin, as before", () => {
    const hint = text("1.2.10", true);
    expect(hint).toContain("for bitcointx to btctx-mcp==1.2.10");
    expect(hint).not.toContain("(or for the");
  });

  it("shows nothing when the version is unknown", () => {
    expect(text(undefined, true)).toBe("");
    expect(text("dev", false)).toBe("");
  });
});
