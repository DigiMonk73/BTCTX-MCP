# Setting up the BitcoinTX MCP server: instructions for an AI assistant

You are reading this because your user wants you connected to their BitcoinTX
ledger. BitcoinTX is a self-hosted, single-user Bitcoin portfolio and tax
tracker. Its MCP server, `btctx-mcp`, runs **on the user's computer** as a
local (stdio) server, started by their AI app, and talks to BitcoinTX over its
API with the user's BitcoinTX login. It gives you tools to read the ledger and
to preview, add, update and delete single transactions.

Their BitcoinTX (**Settings → Connect an AI Assistant**) gave them a prompt
with the values below. If you don't have them, ask.

| Value | Meaning |
|---|---|
| `BTCTX_URL` | Where BitcoinTX answers. macOS app: `http://127.0.0.1:8765`. Docker: the host and port they published. StartOS: the **MCP API** address (`https://….local/api`) |
| `BTCTX_USERNAME` | Their BitcoinTX username |
| `BTCTX_PASSWORD` | Their BitcoinTX password. **Never ask for it in the chat.** Write `YOUR_BITCOINTX_PASSWORD` and have them replace it in the file themselves |
| `BTCTX_CA_BUNDLE` | Only for an `https://` address on their network (StartOS): full path to the server's root CA certificate file (section 1 says where to get it) |
| Server command | `uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP.git@vX.Y.Z#subdirectory=mcp_server" btctx-mcp`; use the ref from their prompt so the server matches their BitcoinTX version |

Name the server `bitcointx`. Ask before installing software or editing any
file, and keep every other server already in a configuration file intact.

## 1. Check the prerequisites

1. **uv**: `uvx --version`. If it's missing, offer to install it: on a Mac
   `brew install uv`, otherwise `curl -LsSf https://astral.sh/uv/install.sh | sh`
   (Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`).
2. **The StartOS certificate** (only for an `https://….local` or IP address):
   StartOS serves BitcoinTX with its own certificate, which this computer
   doesn't trust yet. In StartOS, open BitcoinTX, run the action **Connect an
   AI Assistant**, copy its **Root CA certificate** (the whole
   `-----BEGIN CERTIFICATE-----` … `-----END CERTIFICATE-----` block) and save
   it as `btctx-root-ca.crt` somewhere permanent, such as the home folder.
   `BTCTX_CA_BUNDLE` is that file's full path. The same action also shows the
   password and a ready-made configuration, which can be used instead of
   section 2.
3. **BitcoinTX is reachable**: `curl -s <BTCTX_URL without a trailing /api>/api/health`
   should return JSON with `"status": "ok"` and a `version` of 0.8.0 or later.
   Add `--cacert <certificate file>` for a StartOS address. If it doesn't
   answer: the Mac app must be open; Docker and StartOS must be running and
   reachable from this computer.

If you can't run commands (a chat app without a terminal), skip to section 2
and give the user the steps to follow.

## 2. Add the server to the app you're running in

Use these environment variables (drop `BTCTX_CA_BUNDLE` unless needed):

```
BTCTX_URL=<their address>
BTCTX_USERNAME=<their username>
BTCTX_PASSWORD=YOUR_BITCOINTX_PASSWORD
BTCTX_CA_BUNDLE=<path to the root CA file>
```

### Claude Code

```bash
claude mcp add --scope user bitcointx \
  -e BTCTX_URL='<url>' -e BTCTX_USERNAME='<username>' -e BTCTX_PASSWORD='YOUR_BITCOINTX_PASSWORD' \
  -- uvx --from '<server source>' btctx-mcp
```

Keep the name before the `-e` flags. The server is saved in `~/.claude.json`
under `mcpServers.bitcointx.env`; the user replaces the placeholder there,
then restarts Claude Code (or reconnects it with `/mcp`).

### Claude Desktop

The configuration file is
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS and
`%APPDATA%\Claude\claude_desktop_config.json` on Windows (Settings →
Developer → Edit Config opens it). Merge this into `mcpServers`:

```json
{
  "mcpServers": {
    "bitcointx": {
      "command": "uvx",
      "args": ["--from", "<server source>", "btctx-mcp"],
      "env": {
        "BTCTX_URL": "<url>",
        "BTCTX_USERNAME": "<username>",
        "BTCTX_PASSWORD": "YOUR_BITCOINTX_PASSWORD"
      }
    }
  }
}
```

Claude Desktop starts servers with a minimal `PATH`: put the full path from
`which uvx` in `command` (usually `/opt/homebrew/bin/uvx` or
`~/.local/bin/uvx`). The user replaces the placeholder, then quits and
reopens Claude Desktop.

### Grok Build

```bash
grok mcp add bitcointx \
  -e BTCTX_URL='<url>' -e BTCTX_USERNAME='<username>' -e BTCTX_PASSWORD='YOUR_BITCOINTX_PASSWORD' \
  -- uvx --from '<server source>' btctx-mcp
```

Check the flags with `grok mcp add --help` first. The server is saved in
`~/.grok/config.toml`, where the user replaces the placeholder; `grok mcp doctor`
checks it. Grok Bot and other cloud-hosted assistants can't reach BitcoinTX on
the user's computer or network: use an app that runs on their computer.

### Any other MCP client

A local stdio server: command `uvx`, arguments
`["--from", "<server source>", "btctx-mcp"]`, and the environment variables
above.

## 3. The password

Tell the user the exact file and the text to replace
(`YOUR_BITCOINTX_PASSWORD`), and that the file then holds their password:
anyone who can read it can log in to BitcoinTX. On StartOS the password is the
generated one from the **Show Credentials** action, unless they changed it in
BitcoinTX (**Settings → Reset Username & Password**). If they insist on giving it to
you in the chat, you may write it for them, but say that it has been sent to
your AI provider.

## 4. Check it works

After the app has restarted, call `get_portfolio` (read-only). Balances back
means it works. Before entering any transaction, read `get_ledger_guide`, and
always `preview_transactions` before `add_transactions`.

| Error | Cause |
|---|---|
| `Cannot reach BitcoinTX at …` | Wrong `BTCTX_URL`, or BitcoinTX isn't running. The Mac app logs "Port 8765 is in use" when another program has the port; it then needs `BTCTX_DESKTOP_PORT` and the same port in `BTCTX_URL` |
| `BitcoinTX login failed` | The placeholder is still there, or the username or password is wrong |
| Certificate errors | `BTCTX_CA_BUNDLE` missing or pointing at the wrong file |
| No `/api/import/entries` endpoint | BitcoinTX is older than 0.8.0: update it |
| The app doesn't list the server | It wasn't restarted, or it can't find `uvx` (use the full path) |

More: [README.md](README.md) in this folder.
