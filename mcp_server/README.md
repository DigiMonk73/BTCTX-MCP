# BitcoinTX MCP server

Connect an AI assistant (Claude Desktop, Claude Code, or any MCP client) to
your BitcoinTX ledger. Paste anything, like an exchange confirmation email, a
wallet's transaction history, a block-explorer page or a CSV snippet, or just
describe it ("moved 0.05 BTC from River to my Coldcard yesterday, fee was 2k
sats"). The assistant turns it into transactions, shows you a dry-run preview
with dedup and the resulting gain/loss, and saves them once you confirm.

The server runs **on your computer** and talks to your BitcoinTX instance
(Docker, StartOS or the macOS app) over its normal API, logging in with your
BitcoinTX username and password. Nothing goes through a third party except
what your AI client itself sends to its model.

## Tools

| Tool | What it does |
|------|--------------|
| `get_ledger_guide` | How to map real-world events onto BitcoinTX accounts, types and tax fields |
| `preview_transactions` | Dry run: validate, auto-fill FMV, flag duplicates, simulate FIFO gains and balances. Saves nothing |
| `add_transactions` | Save rows, all-or-nothing; exact duplicates are skipped |
| `list_transactions` | Search by date range, type and account |
| `update_transaction` / `delete_transaction` | Correct one transaction (the ledger is recalculated) |
| `get_portfolio` | Account balances, average cost basis, live BTC price |
| `get_btc_price` | Historical daily or current BTC price |
| `recalculate_ledger` | Rebuild lots and gains from your transactions (same as Settings → Recalculate Ledger) |

There is deliberately no bulk delete.

## Requirements

- BitcoinTX **v0.8.0 or later** (adds the `/api/import/entries` endpoints this server uses)
- Python 3.10+ on the machine running your AI client

## Quick setup: let your AI do it

In BitcoinTX, open **Settings → Connect an AI Assistant** and copy the setup
prompt into your AI app. It carries your address and username and points the
AI to [AI_SETUP.md](AI_SETUP.md), which tells it how to install the server in
Claude Code, Claude Desktop, Grok Build or another MCP client. The password
stays out of the chat: the AI writes `YOUR_BITCOINTX_PASSWORD` and you replace
it in the configuration file. The same section has the Claude Desktop config
and `claude mcp add` command ready to paste if you'd rather do it yourself.

The AI app has to run on your computer (or on your network, for Docker and
StartOS): cloud-hosted assistants such as Grok Bot can't reach BitcoinTX.

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

| Variable | Meaning |
|----------|---------|
| `BTCTX_URL` | Where BitcoinTX is reachable: macOS app `http://127.0.0.1:8765`; Docker the host and port you published, e.g. `http://localhost:8080` or `http://192.168.1.50:8080`; StartOS the **MCP API** address from the service's Interfaces (`https://….local/api`; the **Connect an AI Assistant** action shows it with a ready-made config); from source `http://localhost:8000` |
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
        "BTCTX_URL": "http://192.168.1.50",
        "BTCTX_USERNAME": "your-username",
        "BTCTX_PASSWORD": "your-password"
      }
    }
  }
}
```

If Claude Desktop can't find `btctx-mcp`, use the full path from `which btctx-mcp`.

**macOS desktop app:** use `"BTCTX_URL": "http://127.0.0.1:8765"`. The app listens
there (localhost only) while it's open, so keep BitcoinTX running when you use the
AI. If port 8765 is taken, set `BTCTX_DESKTOP_PORT` for the app and use the same
port here. Username/password are the ones you log in to the app with.

### Claude Code

```bash
claude mcp add bitcointx \
  -e BTCTX_URL=http://192.168.1.50 -e BTCTX_USERNAME=your-username -e BTCTX_PASSWORD=your-password \
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

- Your BitcoinTX password lives in the MCP client config on your computer.
  Anyone who can read that file can log in to BitcoinTX.
- The server exposes read tools plus add/update/delete of single transactions.
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
