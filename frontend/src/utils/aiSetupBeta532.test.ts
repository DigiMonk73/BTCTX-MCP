import { describe, expect, it } from "vitest";
import {
  BETA_SERVER_NAME,
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

// The AI setup a 2.0 pre-release hands out (2.0 plan 7.4, B10a, point 2;
// #532): unpinned, `uvx btctx-mcp` would run the latest 1.x connector, whose
// key file is the installed Mac app's, so an AI set up from the beta could
// write into the tester's real ledger. It pins the beta's own connector
// (PEP 440's 2.0.0bN), links its tag's AI_SETUP.md, and names the server
// apart from the tester's own "bitcointx", which it never replaces.

const BETA = "2.0.0-beta.3";
const mac = { url: "http://127.0.0.1:8767", version: BETA, keyMode: true };
const docker = { url: "http://192.168.1.50:8793", version: BETA };

describe("a beta's AI setup", () => {
  it("pins the beta's own connector and links its tag's guide", () => {
    expect(serverPackage(BETA)).toBe("btctx-mcp==2.0.0b3");
    expect(gitRef(BETA)).toBe("v2.0.0-beta.3");
    expect(setupGuideUrl(BETA)).toBe(
      "https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.0-beta.3/mcp_server/AI_SETUP.md"
    );
  });

  it("hands out the pinned beta connector, under a name of its own, everywhere", () => {
    expect(serverName(BETA)).toBe(BETA_SERVER_NAME);
    expect(BETA_SERVER_NAME).not.toBe(SERVER_NAME);
    for (const input of [mac, docker]) {
      const texts = [buildAiPrompt(input), claudeDesktopConfig(input), claudeCodeCommand(input), grokCommand(input)];
      for (const text of texts) {
        expect(text).toContain("btctx-mcp==2.0.0b3");
        // never an unpinned connector, nor another version
        for (const pin of text.match(/btctx-mcp==[\w.]+/g) ?? []) expect(pin).toBe("btctx-mcp==2.0.0b3");
        expect(text).not.toMatch(/uvx '?btctx-mcp(?!==)/);
        expect(text).not.toContain('"btctx-mcp"');
        expect(text).toContain(BETA_SERVER_NAME);
      }
      expect(buildAiPrompt(input)).toContain(`under the name "${BETA_SERVER_NAME}"`);
      expect(buildAiPrompt(input)).toContain("/blob/v2.0.0-beta.3/mcp_server/AI_SETUP.md");
      expect(JSON.parse(claudeDesktopConfig(input)).mcpServers).toHaveProperty([BETA_SERVER_NAME]);
    }
  });

  it("leaves a release's setup as it was", () => {
    expect(serverName("1.2.10")).toBe("bitcointx");
    expect(serverPackage("2.0.0")).toBe("btctx-mcp==2.0.0");
    expect(gitRef("2.0.0")).toBe("v2.0.0");
  });

  it.each(["2.0.0-rc.1", "2.0.0-beta.0", "2.0.0b1", "2.0.0-beta"])("pins nothing for %s, which no build has", (v) => {
    expect(serverPackage(v)).toBe("btctx-mcp");
    expect(gitRef(v)).toBe("main");
    expect(serverName(v)).toBe("bitcointx");
  });
});
