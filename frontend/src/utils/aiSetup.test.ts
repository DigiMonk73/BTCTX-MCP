import { describe, expect, it } from "vitest";
import {
  KEY_PLACEHOLDER,
  buildAiPrompt,
  claudeCodeCommand,
  claudeDesktopConfig,
  gitRef,
  grokCommand,
  needsCaBundle,
  serverEnv,
} from "./aiSetup";

const server = { url: "http://192.168.1.50:8080", version: "0.9.1" };

describe("gitRef", () => {
  it("pins to the release tag of this app", () => {
    expect(gitRef("0.9.1")).toBe("v0.9.1");
  });

  it("falls back to main when the version is unknown", () => {
    expect(gitRef(undefined)).toBe("main");
    expect(gitRef("dev")).toBe("main");
  });
});

describe("needsCaBundle", () => {
  it("is needed for a StartOS LAN address", () => {
    expect(needsCaBundle("https://adjective-noun.local")).toBe(true);
    expect(needsCaBundle("https://192.168.1.50:3000")).toBe(true);
  });

  it("is not needed for plain http or a public domain", () => {
    expect(needsCaBundle("http://127.0.0.1:8765")).toBe(false);
    expect(needsCaBundle("http://192.168.1.50:8080")).toBe(false);
    expect(needsCaBundle("https://btctx.example.com")).toBe(false);
  });
});

describe("Docker and StartOS: the AI key", () => {
  const outputs = [buildAiPrompt(server), claudeDesktopConfig(server), claudeCodeCommand(server)];

  it("is a placeholder everywhere, never a real value", () => {
    expect(serverEnv(server)).toEqual({ BTCTX_URL: server.url, BTCTX_AI_KEY: KEY_PLACEHOLDER });
    expect(buildAiPrompt(server)).toContain("BTCTX_AI_KEY: don't ask me for it in this chat");
    expect(claudeCodeCommand(server)).toContain(`BTCTX_AI_KEY='${KEY_PLACEHOLDER}'`);
    expect(buildAiPrompt(server)).not.toMatch(/btctx_ak_/);
  });

  it("never asks for or carries a username or password", () => {
    for (const text of outputs) {
      expect(text).not.toContain("BTCTX_PASSWORD");
      expect(text).not.toContain("BTCTX_USERNAME");
    }
    expect(buildAiPrompt(server)).toContain("Never use my BitcoinTX password");
  });

  it("steers the AI to a configuration file over a command in the shell history", () => {
    expect(buildAiPrompt(server)).toMatch(/Prefer your app's configuration file to a terminal command/);
  });
});

describe("buildAiPrompt", () => {
  it("carries the address and a guide and server pinned to this release", () => {
    const prompt = buildAiPrompt(server);
    expect(prompt).toContain("BTCTX_URL: http://192.168.1.50:8080");
    expect(prompt).toContain("https://github.com/DigiMonk73/BTCTX-MCP/blob/v0.9.1/mcp_server/AI_SETUP.md");
    expect(prompt).toContain(
      'uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP.git@v0.9.1#subdirectory=mcp_server" btctx-mcp'
    );
    expect(prompt).not.toContain("BTCTX_CA_BUNDLE");
  });

  it("asks for the certificate on a StartOS address", () => {
    const prompt = buildAiPrompt({ ...server, url: "https://adjective-noun.local" });
    expect(prompt).toContain("BTCTX_CA_BUNDLE");
  });
});

describe("claudeDesktopConfig", () => {
  it("is valid JSON with the server under mcpServers", () => {
    const config = JSON.parse(claudeDesktopConfig(server));
    expect(config.mcpServers.bitcointx).toEqual({
      command: "uvx",
      args: ["--from", "git+https://github.com/DigiMonk73/BTCTX-MCP.git@v0.9.1#subdirectory=mcp_server", "btctx-mcp"],
      env: { BTCTX_URL: "http://192.168.1.50:8080", BTCTX_AI_KEY: KEY_PLACEHOLDER },
    });
  });
});

describe("claudeCodeCommand", () => {
  it("adds the server for every project and puts the name before the env flags", () => {
    const cmd = claudeCodeCommand(server);
    expect(cmd.startsWith("claude mcp add --scope user bitcointx \\\n  -e BTCTX_URL='http://192.168.1.50:8080'")).toBe(true);
    expect(cmd).toContain("-- uvx --from 'git+https://github.com/DigiMonk73/BTCTX-MCP.git@v0.9.1#subdirectory=mcp_server' btctx-mcp");
  });

  it("quotes an address with a quote in it for the shell", () => {
    expect(claudeCodeCommand({ ...server, url: "http://o'neil.local" })).toContain(`BTCTX_URL='http://o'\\''neil.local'`);
  });
});

describe("the Mac app (key file, nothing secret)", () => {
  const keyMode = { url: "http://127.0.0.1:8765", version: "0.9.1", keyMode: true };
  const outputs = [
    buildAiPrompt(keyMode),
    claudeDesktopConfig(keyMode),
    claudeCodeCommand(keyMode),
    grokCommand(keyMode),
  ];

  it("puts no key, password, address or port in any configuration", () => {
    for (const text of outputs) {
      expect(text).not.toContain("BTCTX_PASSWORD");
      expect(text).not.toContain("BTCTX_AI_KEY");
      expect(text).not.toContain(KEY_PLACEHOLDER);
      expect(text).not.toContain("BTCTX_URL");
      expect(text).not.toContain("8765");
    }
    expect(serverEnv(keyMode)).toEqual({});
    expect(JSON.parse(claudeDesktopConfig(keyMode)).mcpServers.bitcointx.env).toBeUndefined();
  });

  it("is one command pinned to this release", () => {
    expect(claudeCodeCommand(keyMode)).toBe(
      "claude mcp add --scope user bitcointx \\\n  -- uvx --from 'git+https://github.com/DigiMonk73/BTCTX-MCP.git@v0.9.1#subdirectory=mcp_server' btctx-mcp",
    );
    expect(grokCommand(keyMode)).toBe(
      "grok mcp add bitcointx -- uvx --from 'git+https://github.com/DigiMonk73/BTCTX-MCP.git@v0.9.1#subdirectory=mcp_server' btctx-mcp",
    );
  });

  it("tells the AI not to ask for the password", () => {
    expect(buildAiPrompt(keyMode)).toMatch(/don't ask me for my password/);
  });
});
