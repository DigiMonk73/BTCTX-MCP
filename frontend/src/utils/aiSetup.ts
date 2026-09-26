/**
 * Text for Settings → Connect an AI Assistant: a prompt the user gives their
 * AI app so it installs the BitcoinTX MCP server itself, and ready-made
 * configurations for doing it by hand.
 *
 * Mac app (keyMode): no URL, username or password at all. The app writes
 * its address and an AI assistant key to a private file the MCP server reads
 * (backend/services/mcp_key.py), so the configuration holds no secret.
 *
 * Server installs (StartOS, Docker): the password is never filled in. The app
 * can't show it (only its hash is stored), and a prompt pasted into an AI chat
 * is sent to the AI provider, so every configuration carries a placeholder the
 * user replaces on their own computer.
 */

export const REPO_URL = "https://github.com/DigiMonk73/BTCTX-MCP";
export const SERVER_NAME = "bitcointx";
export const PASSWORD_PLACEHOLDER = "YOUR_BITCOINTX_PASSWORD";
export const CA_BUNDLE_PLACEHOLDER = "/path/to/root-ca.crt";

export interface AiSetupInput {
  /** Where this BitcoinTX answers, as the browser reached it. */
  url: string;
  username: string;
  /** App version from /api/health; pins the MCP server to the same release. */
  version?: string;
  /** The Mac app: the MCP server finds the app and its key by itself. */
  keyMode?: boolean;
}

/** The release tag matching this app, or main when the version is unknown. */
export function gitRef(version?: string): string {
  return version && /^\d+\.\d+\.\d+$/.test(version) ? `v${version}` : "main";
}

export function serverSource(version?: string): string {
  return `git+${REPO_URL}.git@${gitRef(version)}#subdirectory=mcp_server`;
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

export function serverEnv({ url, username, keyMode }: AiSetupInput): Record<string, string> {
  if (keyMode) return {};
  const env: Record<string, string> = {
    BTCTX_URL: url,
    BTCTX_USERNAME: username,
    BTCTX_PASSWORD: PASSWORD_PLACEHOLDER,
  };
  if (needsCaBundle(url)) env.BTCTX_CA_BUNDLE = CA_BUNDLE_PLACEHOLDER;
  return env;
}

/** The prompt the user pastes into their AI app. */
export function buildAiPrompt(input: AiSetupInput): string {
  if (input.keyMode) {
    return [
      "Connect yourself to my BitcoinTX ledger (a self-hosted Bitcoin portfolio and tax tracker) " +
        `by adding its MCP server, btctx-mcp, to the AI app I'm using with you, under the name "${SERVER_NAME}".`,
      "",
      `Follow this setup guide: ${setupGuideUrl(input.version)}`,
      "",
      "BitcoinTX is the Mac app on this computer. The MCP server finds it by itself, so it needs no " +
        "URL, username or password: don't add any to the configuration, and don't ask me for my password.",
      `- Server command: uvx --from "${serverSource(input.version)}" btctx-mcp`,
      "",
      "If you can't change your own configuration, give me the exact steps instead. " +
        "Once it's connected, call get_portfolio to confirm it works (BitcoinTX must be open).",
    ].join("\n");
  }
  const lines = [
    "Connect yourself to my BitcoinTX ledger (a self-hosted Bitcoin portfolio and tax tracker) " +
      `by adding its MCP server, btctx-mcp, to the AI app I'm using with you, under the name "${SERVER_NAME}".`,
    "",
    `Follow this setup guide: ${setupGuideUrl(input.version)}`,
    "",
    "My details:",
    `- BTCTX_URL: ${input.url}`,
    `- BTCTX_USERNAME: ${input.username}`,
    `- BTCTX_PASSWORD: don't ask me for it in this chat. Put ${PASSWORD_PLACEHOLDER} in the ` +
      "configuration and tell me exactly which file to open to replace it myself.",
  ];
  if (needsCaBundle(input.url)) {
    lines.push(
      "- BTCTX_CA_BUNDLE: this server uses a private certificate; ask me where I saved its root CA " +
        "certificate file (the guide explains)."
    );
  }
  lines.push(
    `- Server command: uvx --from "${serverSource(input.version)}" btctx-mcp`,
    "",
    "If you can't change your own configuration, give me the exact steps instead. " +
      "Once it's connected, call get_portfolio to confirm it works.",
  );
  return lines.join("\n");
}

/** Claude Desktop: Settings → Developer → Edit Config. */
export function claudeDesktopConfig(input: AiSetupInput): string {
  const env = serverEnv(input);
  const config = {
    mcpServers: {
      [SERVER_NAME]: {
        command: "uvx",
        args: ["--from", serverSource(input.version), "btctx-mcp"],
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
    `claude mcp add --scope user ${SERVER_NAME}`,
    ...env,
    `-- uvx --from ${shellQuote(serverSource(input.version))} btctx-mcp`,
  ].join(" \\\n  ");
}

/** Grok Build (Mac app): one command, nothing secret in it. */
export function grokCommand(input: AiSetupInput): string {
  return `grok mcp add ${SERVER_NAME} -- uvx --from ${shellQuote(serverSource(input.version))} btctx-mcp`;
}
