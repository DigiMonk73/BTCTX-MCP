/**
 * Text for Settings → Connect an AI Assistant: a prompt the user gives their
 * AI app so it installs the BitcoinTX MCP server itself, and ready-made
 * configurations for doing it by hand. No password anywhere: the MCP server
 * uses an AI key (backend/services/ai_key.py).
 *
 * Mac app (keyMode): no URL and no key in the configuration. The app writes
 * its address and the AI key to a private file the MCP server reads.
 *
 * Docker, StartOS: the owner creates the AI key in Settings and pastes it
 * into the AI app's settings. The key is never put in these texts: a prompt
 * pasted into an AI chat is sent to the AI provider, so every configuration
 * carries a placeholder the user replaces on their own computer.
 *
 * A 2.0 pre-release, an alpha or a beta (2.0.0-alpha.N, 2.0.0-beta.N; 2.0
 * plan 7.4, B10a), pins its own connector (PEP 440's 2.0.0aN, 2.0.0bN),
 * links its tag's guide, and names the server "bitcointx-preview": unpinned,
 * the latest 1.x connector would run, whose key file is the installed Mac
 * app's, and under "bitcointx" the AI app's entry for the tester's own
 * BitcoinTX would be replaced.
 */

import { macApp, prereleaseParts } from "./prereleaseVersion";

export const REPO_URL = "https://github.com/DigiMonk73/BTCTX-MCP";
export const SERVER_NAME = "bitcointx";
export const PREVIEW_SERVER_NAME = "bitcointx-preview";
export const KEY_PLACEHOLDER = "YOUR_BITCOINTX_AI_KEY";
export const CA_BUNDLE_PLACEHOLDER = "/path/to/root-ca.crt";

export interface AiSetupInput {
  /** Where this BitcoinTX answers, as the browser reached it. */
  url: string;
  /** App version from /api/health; the setup guide is read at the same release. */
  version?: string;
  /** The Mac app: the MCP server finds the app and its key by itself. */
  keyMode?: boolean;
}

const RELEASE = /^\d+\.\d+\.\d+$/;

/** The release (or pre-release) tag matching this app, or main when the version is unknown. */
export function gitRef(version?: string): string {
  return version && (RELEASE.test(version) || prereleaseParts(version)) ? `v${version}` : "main";
}

/** The name the AI app knows this BitcoinTX by: a pre-release's apart from the tester's own. */
export function serverName(version?: string): string {
  return prereleaseParts(version) ? PREVIEW_SERVER_NAME : SERVER_NAME;
}

/**
 * The MCP server from PyPI, pinned to this app's release (btctx-mcp==X.Y.Z,
 * an alpha's btctx-mcp==X.Y.ZaN, a beta's X.Y.ZbN): the AI app runs exactly that version and
 * asks nothing new at each start. When BitcoinTX is updated, the server's
 * replies say which version to set.
 */
export function serverPackage(version?: string): string {
  const pre = prereleaseParts(version);
  if (pre) return `btctx-mcp==${pre.release}${pre.stage}${pre.n}`;
  return version && RELEASE.test(version) ? `btctx-mcp==${version}` : "btctx-mcp";
}

export function setupGuideUrl(version?: string): string {
  return `${REPO_URL}/blob/${gitRef(version)}/mcp_server/AI_SETUP.md`;
}

/**
 * An https address on the local network (StartOS: https://….local or an IP)
 * uses a certificate the user's computer doesn't trust yet, so the server
 * needs BTCTX_CA_BUNDLE. Public domains have a normal certificate.
 */
export function needsCaBundle(url: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return false;
  }
  if (parsed.protocol !== "https:") return false;
  const host = parsed.hostname;
  return host.endsWith(".local") || /^\d{1,3}(\.\d{1,3}){3}$/.test(host) || host.startsWith("[");
}

export function serverEnv({ url, keyMode }: AiSetupInput): Record<string, string> {
  if (keyMode) return {};
  const env: Record<string, string> = { BTCTX_URL: url, BTCTX_AI_KEY: KEY_PLACEHOLDER };
  if (needsCaBundle(url)) env.BTCTX_CA_BUNDLE = CA_BUNDLE_PLACEHOLDER;
  return env;
}

/** The prompt the user pastes into their AI app. */
export function buildAiPrompt(input: AiSetupInput): string {
  const intro = [
    "Connect yourself to my BitcoinTX ledger (a self-hosted Bitcoin portfolio and tax tracker) " +
      `by adding its MCP server, btctx-mcp, to the AI app I'm using with you, under the name "${serverName(input.version)}".`,
    "",
    `Follow this setup guide: ${setupGuideUrl(input.version)}`,
    "",
  ];
  const outro = [
    "",
    // Off in a new install: the first try failed with "AI access is turned off" (#676).
    // A pre-release's Mac app has its own switch, never the installed app's
    'AI access is off until I turn it on: before you check it works, ask me to turn on ' +
      `"Let AI assistants use BitcoinTX" in ${input.keyMode ? macApp(input.version) : "BitcoinTX"} ` +
      "Settings → Connect an AI Assistant.",
    "If you can't change your own configuration, give me the exact steps instead. " +
      "Once it's connected, call get_portfolio to confirm it works" +
      (input.keyMode ? ` (${macApp(input.version)} must be open).` : "."),
  ];
  if (input.keyMode) {
    return [
      ...intro,
      // A pre-release's own Mac app, beside BitcoinTX: the server reads its key file
      `BitcoinTX is the Mac app ${macApp(input.version) === "BitcoinTX" ? "" : `${macApp(input.version)} `}` +
        "on this computer. The MCP server finds it by itself, so it needs no " +
        "URL, key or password: don't add any to the configuration, and don't ask me for my password.",
      `- Server command: uvx ${serverPackage(input.version)}`,
      ...outro,
    ].join("\n");
  }
  const lines = [
    ...intro,
    "My details:",
    `- BTCTX_URL: ${input.url}`,
    `- BTCTX_AI_KEY: don't ask me for it in this chat. Put ${KEY_PLACEHOLDER} in the ` +
      "configuration and tell me exactly which file to open to paste my AI key there myself " +
      "(I create it in BitcoinTX Settings). Prefer your app's configuration file to a terminal " +
      "command, which would keep the key in the shell history. Never use my BitcoinTX password.",
  ];
  if (needsCaBundle(input.url)) {
    lines.push(
      "- BTCTX_CA_BUNDLE: this server uses a private certificate; ask me where I saved its root CA " +
        "certificate file (the guide explains)."
    );
  }
  lines.push(`- Server command: uvx ${serverPackage(input.version)}`, ...outro);
  return lines.join("\n");
}

/** Claude Desktop (Settings → Developer → Edit Config) and LM Studio (mcp.json). */
export function claudeDesktopConfig(input: AiSetupInput): string {
  const env = serverEnv(input);
  const config = {
    mcpServers: {
      [serverName(input.version)]: {
        command: "uvx",
        args: [serverPackage(input.version)],
        ...(Object.keys(env).length ? { env } : {}),
      },
    },
  };
  return JSON.stringify(config, null, 2);
}

function shellQuote(value: string): string {
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

/** Claude Code: one command, available in every project (user scope). */
export function claudeCodeCommand(input: AiSetupInput): string {
  const env = Object.entries(serverEnv(input)).map(([k, v]) => `-e ${k}=${shellQuote(v)}`);
  return [
    `claude mcp add --scope user ${serverName(input.version)}`,
    ...env,
    `-- uvx ${shellQuote(serverPackage(input.version))}`,
  ].join(" \\\n  ");
}

/** Grok Build (Mac app): one command, nothing secret in it. */
export function grokCommand(input: AiSetupInput): string {
  return `grok mcp add ${serverName(input.version)} -- uvx ${shellQuote(serverPackage(input.version))}`;
}
