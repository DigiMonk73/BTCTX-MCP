import { describe, expect, it } from "vitest";
import {
  PREVIEW_SERVER_NAME,
  SERVER_NAME,
  buildAiPrompt,
  claudeCodeCommand,
  claudeDesktopConfig,
  gitRef,
  grokCommand,
  serverName,
  serverPackage,
  setupGuideUrl,
} from "./aiSetup";
import { macApp, prereleaseParts } from "./prereleaseVersion";

// The AI setup a 2.0 pre-release hands out, an alpha or a beta (2.0 plan 7.4,
// B10a, point 2; #532; #251's decision 28): unpinned, `uvx btctx-mcp` would
// run the latest 1.x connector, whose key file is the installed Mac app's,
// so an AI set up from a pre-release could write into the tester's real
// ledger. It pins the pre-release's own connector (PEP 440's 2.0.0aN or
// 2.0.0bN), links its tag's AI_SETUP.md, and names the server apart from the
// tester's own "bitcointx".

describe.each([
  ["2.0.0-beta.3", "btctx-mcp==2.0.0b3"],
  ["2.0.0-alpha.2", "btctx-mcp==2.0.0a2"],
])("%s's AI setup", (version, pin) => {
  const mac = { url: "http://127.0.0.1:8767", version, keyMode: true };
  const docker = { url: "http://192.168.1.50:8793", version };

  it("pins the pre-release's own connector and links its tag's guide", () => {
    expect(serverPackage(version)).toBe(pin);
    expect(gitRef(version)).toBe(`v${version}`);
    expect(setupGuideUrl(version)).toBe(`https://github.com/DigiMonk73/BTCTX-MCP/blob/v${version}/mcp_server/AI_SETUP.md`);
  });

  it("hands out the pinned connector, under a name of its own, everywhere", () => {
    expect(serverName(version)).toBe(PREVIEW_SERVER_NAME);
    expect(PREVIEW_SERVER_NAME).not.toBe(SERVER_NAME);
    for (const input of [mac, docker]) {
      const texts = [buildAiPrompt(input), claudeDesktopConfig(input), claudeCodeCommand(input), grokCommand(input)];
      for (const text of texts) {
        expect(text).toContain(pin);
        // never an unpinned connector, nor another version
        for (const found of text.match(/btctx-mcp==[\w.]+/g) ?? []) expect(found).toBe(pin);
        expect(text).not.toMatch(/uvx '?btctx-mcp(?!==)/);
        expect(text).not.toContain('"btctx-mcp"');
        expect(text).toContain(PREVIEW_SERVER_NAME);
      }
      expect(buildAiPrompt(input)).toContain(`under the name "${PREVIEW_SERVER_NAME}"`);
      expect(buildAiPrompt(input)).toContain(`/blob/v${version}/mcp_server/AI_SETUP.md`);
      expect(JSON.parse(claudeDesktopConfig(input)).mcpServers).toHaveProperty([PREVIEW_SERVER_NAME]);
    }
  });

  it("merged into an AI app's config beside 1.x's, leaves the 1.x entry as it was (the owner's requirement)", () => {
    const onex = JSON.parse(claudeDesktopConfig({ ...mac, version: "1.2.10" })).mcpServers;
    const preview = JSON.parse(claudeDesktopConfig(mac)).mcpServers;
    const merged = { ...onex, ...preview };
    expect(Object.keys(merged).sort()).toEqual([SERVER_NAME, PREVIEW_SERVER_NAME].sort());
    expect(merged[SERVER_NAME]).toEqual(onex[SERVER_NAME]);
    expect(merged[SERVER_NAME].args).toEqual(["btctx-mcp==1.2.10"]);
  });

  it("on a Mac, names BitcoinTX Preview, the app the connector finds", () => {
    const prompt = buildAiPrompt(mac);
    expect(prompt).toContain("BitcoinTX is the Mac app BitcoinTX Preview on this computer.");
    expect(prompt).toContain("(BitcoinTX Preview must be open).");
  });
});

describe("a version's form", () => {
  it("reads an alpha's or a beta's numbers, and nothing else", () => {
    expect(prereleaseParts("2.0.0-beta.12")).toEqual({ release: "2.0.0", stage: "b", n: "12" });
    expect(prereleaseParts("2.0.0-alpha.1")).toEqual({ release: "2.0.0", stage: "a", n: "1" });
    for (const v of ["2.0.0", "2.0.0-beta.0", "2.0.0-alpha.01", "2.0.0b1", "2.0.0-rc.1", undefined]) {
      expect(prereleaseParts(v)).toBeNull();
    }
    expect(macApp("2.0.0-alpha.1")).toBe("BitcoinTX Preview");
    expect(macApp("2.0.0")).toBe("BitcoinTX");
  });

  it("leaves a release's setup as it was", () => {
    expect(serverName("1.2.10")).toBe("bitcointx");
    expect(serverPackage("2.0.0")).toBe("btctx-mcp==2.0.0");
    expect(gitRef("2.0.0")).toBe("v2.0.0");
    const mac = buildAiPrompt({ url: "http://127.0.0.1:8765", version: "1.2.10", keyMode: true });
    expect(mac).toContain("BitcoinTX is the Mac app on this computer.");
    expect(mac).toContain("(BitcoinTX must be open).");
  });

  it.each(["2.0.0-rc.1", "2.0.0-beta.0", "2.0.0b1", "2.0.0-beta", "2.0.0-alpha"])("pins nothing for %s, which no build has", (v) => {
    expect(serverPackage(v)).toBe("btctx-mcp");
    expect(gitRef(v)).toBe("main");
    expect(serverName(v)).toBe("bitcointx");
  });
});

describe("2.0.0, the release (2.0 plan 6.3)", () => {
  const release = { url: "http://127.0.0.1:8765", version: "2.0.0", keyMode: true };

  it("is BitcoinTX again: the name bitcointx, its own connector and tag", () => {
    expect(macApp("2.0.0")).toBe("BitcoinTX");
    const entry = JSON.parse(claudeDesktopConfig(release)).mcpServers;
    expect(Object.keys(entry)).toEqual([SERVER_NAME]);
    expect(entry[SERVER_NAME].args).toEqual(["btctx-mcp==2.0.0"]);
    expect(buildAiPrompt(release)).toContain("/blob/v2.0.0/mcp_server/AI_SETUP.md");
    expect(buildAiPrompt(release)).not.toContain(PREVIEW_SERVER_NAME);
  });
});
