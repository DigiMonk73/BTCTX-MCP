# Setting up the BitcoinTX MCP server: instructions for an AI assistant

You are reading this because your user wants you connected to their BitcoinTX
ledger. BitcoinTX is a self-hosted, single-user Bitcoin portfolio and tax
tracker. Its MCP server, `btctx-mcp`, runs **on the user's computer** as a
local (stdio) server, started by their AI app, and talks to BitcoinTX over its
API. It gives you tools to read the ledger and to preview, add, update and
delete single transactions.

**Which setup?** Their BitcoinTX (**Settings → Connect an AI Assistant**) gave
them a prompt.

- **The BitcoinTX Mac app on this computer** (0.9.2 or later; the prompt says
  the server "finds it by itself"): no URL, username or password. The app
  writes its address and an AI assistant key to a private file
  (`~/Library/Application Support/BitcoinTX/mcp.json`) that the server reads.
  **Never put a password in the configuration.** Do section 1 (only uv) and
  section 2A, then section 4.
- **A server install** (StartOS, Docker, or a Mac app older than 0.9.2): the
  values below. If you don't have them, ask. Do sections 1, 2B, 3 and 4.

| Value | Meaning |
|---|---|
| `BTCTX_URL` | Where BitcoinTX answers. Docker: the host and port they published. StartOS: the **MCP API** address (`https://….local/api`). Older Mac app: `http://127.0.0.1:8765` |
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
   section 2B.
3. **BitcoinTX is reachable**: `curl -s <BTCTX_URL without a trailing /api>/api/health`
   should return JSON with `"status": "ok"` and a `version` of 0.8.0 or later.
   Add `--cacert <certificate file>` for a StartOS address. If it doesn't
   answer: the Mac app must be open; Docker and StartOS must be running and
   reachable from this computer.

If you can't run commands (a chat app without a terminal), skip to section 2A or 2B
and give the user the steps to follow.

## 2A. The Mac app: add the server, nothing secret

One command, no environment variables. BitcoinTX must be open when the AI
uses it.

- **Claude Code:** `claude mcp add --scope user bitcointx -- uvx --from '<server source>' btctx-mcp`
- **Grok Build:** `grok mcp add bitcointx -- uvx --from '<server source>' btctx-mcp`
- **Claude Desktop:** merge
  `{"mcpServers": {"bitcointx": {"command": "uvx", "args": ["--from", "<server source>", "btctx-mcp"]}}}`
  into its configuration file (section 2B says where, and about the full `uvx`
  path), then quit and reopen it.
- **Any other MCP client:** command `uvx`, arguments
  `["--from", "<server source>", "btctx-mcp"]`, no environment variables.

If the user had set it up with a password before: remove the
`BTCTX_URL`/`BTCTX_USERNAME`/`BTCTX_PASSWORD` lines (or remove the server and
add it again with the command above), check a read works (section 4), then
suggest they change their BitcoinTX password, since the old one sat in a
plain-text file. The key can be turned off or reset in **Settings → Connect
an AI Assistant**; after a reset the server picks up the new key by itself.

## 2B. A server install: add the server to the app you're running in

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

## 3. The password (server installs only)

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
| `Cannot reach BitcoinTX …` | The error lists where the server looked. Mac app: open BitcoinTX (it writes `mcp.json` when it starts); if it shows a "running on port N this session" banner, another program had port 8765: quit BitcoinTX, close that program and reopen it. Server install: wrong `BTCTX_URL`, or BitcoinTX isn't running |
| `AI assistant access is turned off` | Turned off in BitcoinTX **Settings → Connect an AI Assistant** |
| `BitcoinTX login failed` | The placeholder is still there, or the username or password is wrong |
| Certificate errors | `BTCTX_CA_BUNDLE` missing or pointing at the wrong file |
| No `/api/import/entries` endpoint | BitcoinTX is older than 0.8.0: update it |
| The app doesn't list the server | It wasn't restarted, or it can't find `uvx` (use the full path) |

More: [README.md](README.md) in this folder.
