import { describe, expect, it } from "vitest";
import {
  PASSWORD_PLACEHOLDER,
  buildAiPrompt,
  claudeCodeCommand,
  claudeDesktopConfig,
  gitRef,
  needsCaBundle,
  serverEnv,
} from "./aiSetup";

const mac = { url: "http://127.0.0.1:8765", username: "satoshi", version: "0.9.1" };

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

describe("the password", () => {
  it("is a placeholder everywhere, never a real value", () => {
    expect(serverEnv(mac).BTCTX_PASSWORD).toBe(PASSWORD_PLACEHOLDER);
    expect(buildAiPrompt(mac)).toContain(`don't ask me for it in this chat`);
    expect(claudeCodeCommand(mac)).toContain(`BTCTX_PASSWORD='${PASSWORD_PLACEHOLDER}'`);
  });
});

describe("buildAiPrompt", () => {
  it("carries the address, login and a guide and server pinned to this release", () => {
    const prompt = buildAiPrompt(mac);
    expect(prompt).toContain("BTCTX_URL: http://127.0.0.1:8765");
    expect(prompt).toContain("BTCTX_USERNAME: satoshi");
    expect(prompt).toContain("https://github.com/DigiMonk73/BTCTX-MCP/blob/v0.9.1/mcp_server/AI_SETUP.md");
    expect(prompt).toContain(
      'uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP.git@v0.9.1#subdirectory=mcp_server" btctx-mcp'
    );
    expect(prompt).not.toContain("BTCTX_CA_BUNDLE");
  });

  it("asks for the certificate on a StartOS address", () => {
    const prompt = buildAiPrompt({ ...mac, url: "https://adjective-noun.local" });
    expect(prompt).toContain("BTCTX_CA_BUNDLE");
  });
});

describe("claudeDesktopConfig", () => {
  it("is valid JSON with the server under mcpServers", () => {
    const config = JSON.parse(claudeDesktopConfig(mac));
    expect(config.mcpServers.bitcointx).toEqual({
      command: "uvx",
      args: ["--from", "git+https://github.com/DigiMonk73/BTCTX-MCP.git@v0.9.1#subdirectory=mcp_server", "btctx-mcp"],
      env: {
        BTCTX_URL: "http://127.0.0.1:8765",
        BTCTX_USERNAME: "satoshi",
        BTCTX_PASSWORD: PASSWORD_PLACEHOLDER,
      },
    });
  });
});

describe("claudeCodeCommand", () => {
  it("adds the server for every project and puts the name before the env flags", () => {
    const cmd = claudeCodeCommand(mac);
    expect(cmd.startsWith("claude mcp add --scope user bitcointx \\\n  -e BTCTX_URL='http://127.0.0.1:8765'")).toBe(true);
    expect(cmd).toContain("-- uvx --from 'git+https://github.com/DigiMonk73/BTCTX-MCP.git@v0.9.1#subdirectory=mcp_server' btctx-mcp");
  });

  it("quotes a username with a quote in it for the shell", () => {
    expect(claudeCodeCommand({ ...mac, username: "o'neil" })).toContain(`BTCTX_USERNAME='o'\\''neil'`);
  });
});
