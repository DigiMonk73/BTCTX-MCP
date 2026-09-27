# BitcoinTX MCP server

Connect an AI assistant (Claude Desktop, Claude Code, or any MCP client) to
your BitcoinTX ledger. Paste anything, like an exchange confirmation email, a
wallet's transaction history, a block-explorer page or a CSV snippet, or just
describe it ("moved 0.05 BTC from River to my Coldcard yesterday, fee was 2k
sats"). The assistant turns it into transactions, shows you a dry-run preview
with dedup and the resulting gain/loss, and saves them once you confirm.

The server runs **on your computer** and talks to your BitcoinTX instance
over its normal API. With the Mac app it uses an AI assistant key the app
keeps in a private file, never your password; with Docker or StartOS it logs
in with your BitcoinTX username and password.

**What the AI's model sees:** everything the tools return (transactions,
balances, gains, the review list) and everything you paste into the chat.
The MCP server itself sends nothing anywhere else, but your AI app sends the
conversation to its model. With a cloud AI that is the provider's servers;
see [Privacy: cloud or local model](#privacy-cloud-or-local-model).

## Tools

| Tool | What it does |
|------|--------------|
| `get_ledger_guide` | How to map real-world events onto BitcoinTX accounts, types and tax fields |
| `preview_transactions` | Dry run: validate, auto-fill FMV, flag duplicates, simulate FIFO gains and balances. Saves nothing |
| `add_transactions` | Save rows, all-or-nothing; exact duplicates are skipped |
| `list_transactions` | Search by date range, type and account |
| `update_transaction` / `delete_transaction` | Correct one transaction (the ledger is recalculated). An update can also set `broker_reporting` (which Form 8949 box a sale goes in) and `fee_usd` |
| `get_portfolio` | Account balances, average cost basis, live BTC price (when live data is on in Settings → Privacy & Network), tax timezone |
| `get_btc_price` | Historical daily or current BTC price |
| `recalculate_ledger` | Rebuild lots and gains from your transactions (same as Settings → Recalculate Ledger) |
| `review_ledger` | Read-only list of saved transactions worth a second look (same as Settings → Ledger Review). Changes nothing; fee-value fixes are made in Settings |

There is deliberately no bulk delete.

## Requirements

- BitcoinTX **v0.8.0 or later** (adds the `/api/import/entries` endpoints this
  server uses). The Mac app's key file, `review_ledger` and `fee_usd` need
  **v0.9.2 or later**. Install the server from the tag that matches your
  BitcoinTX version (`…BTCTX-MCP.git@vX.Y.Z#subdirectory=mcp_server`); the
  setup prompt in Settings does this for you.
- Python 3.10+ on the machine running your AI client

## Quick setup: let your AI do it

In BitcoinTX, open **Settings → Connect an AI Assistant** and copy the setup
prompt into your AI app. It carries your address and username and points the
AI to [AI_SETUP.md](AI_SETUP.md), which tells it how to install the server in
Claude Code, Claude Desktop, Grok Build or another MCP client. The password
stays out of the chat: the AI writes `YOUR_BITCOINTX_PASSWORD` and you replace
it in the configuration file. The same section has the Claude Desktop config
and `claude mcp add` command (and, for the Mac app, a Grok Build command)
ready to paste if you'd rather do it yourself.

The AI app has to run on your computer (or on your network, for Docker and
StartOS): cloud-hosted assistants such as Grok Bot can't reach BitcoinTX.
Running on your computer doesn't make the AI's model local, though: read the
next section before you connect a cloud AI.

## Privacy: cloud or local model

An MCP server gives the AI your data to read. Here that means your
transaction history, balances, cost basis and gains, plus whatever you paste
(exchange emails, wallet histories, addresses, txids). Where it goes depends
on the model behind your AI app, not on this server:

- **Cloud AI** (Claude Desktop, Claude Code, Grok Build and most others): the
  conversation, tool results included, is sent to the provider's servers and
  handled under its privacy terms. Your password or AI assistant key is not
  sent: it stays in the configuration on your computer.
- **Local model:** nothing leaves your computer. Use an app that runs MCP
  servers with a model on your own machine, for example
  [LM Studio](https://lmstudio.ai/docs/app/mcp) (0.3.17 or later) or
  [Goose](https://goose-docs.ai/) with [Ollama](https://ollama.com/).

Access: in the Mac app, **Settings → Connect an AI Assistant → Let AI
assistants use BitcoinTX** is off by default: nothing can use the key until
you turn it on; on Docker and
StartOS the server logs in with your password, so remove it from your AI app
(or change the password) to stop it.

If you want BitcoinTX's data to stay private, use a local model, or use a
cloud AI only with a test ledger. Keeping a cloud AI away from real data
isn't something BitcoinTX can enforce once it's connected.

### Using a local model

Pick a model that handles tool calls well (for example a recent Qwen model
of 8B parameters or more) and give it a context window of at least 16K tokens:
the ledger guide and tool results don't fit in Ollama's small default.
Smaller models make more mistakes, so read every preview before you confirm.

**LM Studio:** Program tab → Install → Edit `mcp.json`, and add the same block
as for Claude Desktop (below). For the Mac app:

```json
{
  "mcpServers": {
    "bitcointx": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/DigiMonk73/BTCTX-MCP.git@vX.Y.Z#subdirectory=mcp_server", "btctx-mcp"]
    }
  }
}
```

Use the full path from `which uvx` if LM Studio can't find it. For Docker or
StartOS add the `env` block with `BTCTX_URL`, `BTCTX_USERNAME` and
`BTCTX_PASSWORD`.

**Goose:** `goose configure` → choose Ollama as the provider; then
`goose configure` → Add Extension → Command-line Extension, with the command
`uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP.git@vX.Y.Z#subdirectory=mcp_server" btctx-mcp`
(and the three `BTCTX_` variables for a server install).

## Install

```bash
# from a clone of this repo
pip install ./mcp_server
# or without cloning
pip install "git+https://github.com/DigiMonk73/BTCTX-MCP.git#subdirectory=mcp_server"
```

This installs a `btctx-mcp` command. `uvx` works too:
`uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP.git#subdirectory=mcp_server" btctx-mcp`.

## Configure

**The BitcoinTX Mac app (0.9.2+): nothing to configure.** With no
`BTCTX_USERNAME`/`BTCTX_PASSWORD` set, the server reads
`~/Library/Application Support/BitcoinTX/mcp.json`, which the app writes when
it starts (owner-only): its address and an AI assistant key, never your
password. Turn on **Settings → Connect an AI Assistant → Let AI assistants use
BitcoinTX** first (off by default), and keep BitcoinTX open while you use the
AI. The same section turns access off again or resets the key (the server picks up a
new key by itself). `BTCTX_MCP_FILE` points at another file.

**A server install (StartOS, Docker, from source):**

| Variable | Meaning |
|----------|---------|
| `BTCTX_URL` | Where BitcoinTX is reachable: Docker the host and port you published, e.g. `http://localhost:8080` or `http://192.168.1.50:8080`; StartOS the **MCP API** address from the service's Interfaces (`https://….local/api`; the **Connect an AI Assistant** action shows it with a ready-made config); from source `http://localhost:8000` |
| `BTCTX_USERNAME` / `BTCTX_PASSWORD` | Your BitcoinTX login |
| `BTCTX_VERIFY_TLS` | `false` to accept a self-signed certificate (StartOS `.local` addresses) |
| `BTCTX_CA_BUNDLE` | Or: path to the CA certificate that signed it (StartOS lets you download its root CA). Safer than disabling verification |

### Claude Desktop

Settings → Developer → Edit Config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "bitcointx": {
      "command": "btctx-mcp",
      "env": {
        "BTCTX_URL": "http://192.168.1.50:8080",
        "BTCTX_USERNAME": "your-username",
        "BTCTX_PASSWORD": "your-password"
      }
    }
  }
}
```

If Claude Desktop can't find `btctx-mcp`, use the full path from `which btctx-mcp`.

**macOS desktop app:** leave out `env` entirely:
`{"mcpServers": {"bitcointx": {"command": "btctx-mcp"}}}`. The server finds the
running app and its key by itself.

### Claude Code

```bash
claude mcp add --scope user bitcointx \
  -e BTCTX_URL=http://192.168.1.50:8080 -e BTCTX_USERNAME=your-username -e BTCTX_PASSWORD=your-password \
  -- btctx-mcp
```

## Using it

> Here's my River email: "You bought 0.00231 BTC for $150.00 (fee $1.49) on Mar 3"

> I withdrew everything from River to my Trezor on March 10, network fee 1,800 sats

> Got paid 250k sats for a logo design on 2024-05-02, went straight to cold storage

The assistant asks when something tax-relevant is ambiguous (is that address
your own wallet or someone else's? bank-funded or from your River cash
balance?), previews, then saves once you confirm. Your AI client will also ask
you to approve each tool call unless you tell it not to.

## Security notes

- Mac app: the AI assistant key sits in `mcp.json`, readable only by you. It
  works only from this computer, and never for backup, restore, imports or
  delete-all. Settings → Connect an AI Assistant turns it off or resets it.
- Docker/StartOS: your BitcoinTX password lives in the MCP client config on
  your computer. Anyone who can read that file can log in to BitcoinTX.
- With a cloud AI, what the tools return goes to the provider (see
  [Privacy](#privacy-cloud-or-local-model)).
- The server exposes read tools, `review_ledger`, `recalculate_ledger`, and
  add/update/delete of single transactions.
  Every write is visible in BitcoinTX. Take a backup (Settings → Backup &
  Restore, or `scripts/backup-db.sh` on a server) before a large import.

## Development

```bash
# from the repo root
pip install -r backend/requirements.txt -r requirements-dev.txt ./mcp_server
mkdir -p frontend/dist
pytest mcp_server/tests backend/tests/test_entry_import.py
```

The tests run an MCP client against this server, which calls the real FastAPI
app in-process on a temporary database. Price lookups are stubbed.
