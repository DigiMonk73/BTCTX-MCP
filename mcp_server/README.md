# BitcoinTX MCP server

Connect an AI assistant (Claude Desktop, Claude Code, or any MCP client) to
your BitcoinTX ledger. Paste anything, like an exchange confirmation email, a
wallet's transaction history, a block-explorer page or a CSV snippet, or just
describe it ("moved 0.05 BTC from River to my Coldcard yesterday, fee was 2k
sats"). The assistant turns it into transactions, shows you a dry-run preview
with dedup and the resulting gain/loss, and saves them once you confirm.

The server runs **on your computer** and talks to your BitcoinTX instance
over its normal API with an **AI key**, never your password. The Mac app
keeps the key in a private file the server reads; with Docker or StartOS you
create the key in BitcoinTX Settings and paste it into your AI app's
settings.

**What the AI's model sees:** everything the tools return (transactions,
balances, gains, the review list) and everything you paste into the chat.
The MCP server itself sends nothing anywhere else. When a preview fills in a
value, BitcoinTX asks only the price source you chose in Settings → Privacy &
Network (your own mempool server, public price sites, or nothing), and no
request names a transaction date. Your AI app sends the conversation to its
model. With a cloud AI that is the provider's servers;
see [Privacy: cloud or local model](https://github.com/DigiMonk73/BTCTX-MCP/blob/main/mcp_server/README.md#privacy-cloud-or-local-model).

## Tools

| Tool | What it does |
|------|--------------|
| `get_ledger_guide` | How to map real-world events onto BitcoinTX accounts, types and tax fields |
| `preview_transactions` | Dry run: validate, auto-fill FMV, flag duplicates, simulate FIFO gains and balances. Saves nothing |
| `add_transactions` | Save rows, all-or-nothing; exact duplicates are skipped |
| `list_transactions` | Search by date range, type and account |
| `update_transaction` / `delete_transaction` | Correct one transaction (the ledger is recalculated). An update can also set `broker_reporting` (which Form 8949 box a sale goes in) and `fee_usd` |
| `get_portfolio` | Account balances, average cost basis, live BTC price (from the price source chosen in Settings → Privacy & Network), tax timezone |
| `get_btc_price` | Historical daily or current BTC price |
| `recalculate_ledger` | Rebuild lots and gains from your transactions (same as Settings → Recalculate Ledger) |
| `review_ledger` | Read-only list of saved transactions worth a second look (same as Settings → Ledger Review). Changes nothing; fee-value fixes are made in Settings |
| `backup_ledger` | A copy of the database in BitcoinTX's `backups` folder on your server, as a safety net before a large change (the newest 3 are kept, one a minute). Restoring one is up to you |

There is deliberately no bulk delete.

## Requirements

- BitcoinTX **v1.0.3 or later** on Docker and StartOS (the AI key); the Mac
  app **v0.9.2 or later** (its key file). `backup_ledger` needs v1.0.3.
  Install the server pinned to your BitcoinTX release (`btctx-mcp==X.Y.Z`
  from PyPI; the setup prompt in Settings fills in your version), so your AI
  app runs exactly that version. Versions before 1.2.0 aren't on PyPI: use
  `uvx --from "git+https://github.com/DigiMonk73/BTCTX-MCP.git@vX.Y.Z#subdirectory=mcp_server" btctx-mcp`.
  When the server and your BitcoinTX are different versions, every tool
  reply starts with a line saying so and what to change.
- Python 3.10+ on the machine running your AI client

## Quick setup: let your AI do it

In BitcoinTX, open **Settings → Connect an AI Assistant** and copy the setup
prompt into your AI app. It carries your address and points the AI to
[AI_SETUP.md](https://github.com/DigiMonk73/BTCTX-MCP/blob/main/mcp_server/AI_SETUP.md), which tells it how to install the server in
Claude Code, Claude Desktop, Grok Build or another MCP client. On Docker and
StartOS, create the AI key in the same section first; it stays out of the
chat: the AI writes `YOUR_BITCOINTX_AI_KEY` and you paste the key into the
configuration file. The section also has the Claude Desktop config and
`claude mcp add` command (and, for the Mac app, a Grok Build command) ready
to paste if you'd rather do it yourself.

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
  handled under its privacy terms. Your AI key is not sent: it stays in the
  configuration on your computer.
- **Local model:** what the AI reads stays on your machine. BitcoinTX itself
  asks only the price source you chose (your own mempool server or public
  price sites; Settings → Privacy & Network). Use an app that runs MCP
  servers with a model on your own machine, for example
  [LM Studio](https://lmstudio.ai/docs/app/mcp) (0.3.17 or later) or
  [Goose](https://goose-docs.ai/) with [Ollama](https://ollama.com/).

Access: **Settings → Connect an AI Assistant → Let AI assistants use
BitcoinTX** is off by default on every edition: nothing can use the key until
you turn it on. Turn it off, or revoke the key (Docker, StartOS), to stop the
AI.

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
      "args": ["btctx-mcp==X.Y.Z"]
    }
  }
}
```

Use the full path from `which uvx` if LM Studio can't find it. For Docker or
StartOS add the `env` block with `BTCTX_URL` and `BTCTX_AI_KEY` (see
Configure).

**Goose:** `goose configure` → choose Ollama as the provider; then
`goose configure` → Add Extension → Command-line Extension, with the command
`uvx btctx-mcp==X.Y.Z`
(and `BTCTX_URL` and `BTCTX_AI_KEY` for Docker or StartOS).

## Install

```bash
uvx btctx-mcp==X.Y.Z            # your BitcoinTX version; nothing to install
pip install btctx-mcp==X.Y.Z    # or a btctx-mcp command of your own
pip install ./mcp_server        # or from a clone of the repo
```

## Configure

**The BitcoinTX Mac app (0.9.2+): nothing to configure.** With no
`BTCTX_AI_KEY` set, the server reads
`~/Library/Application Support/BitcoinTX/mcp.json`, which the app writes when
it starts (owner-only): its address and the AI key, never your password.
Turn on **Settings → Connect an AI Assistant → Let AI assistants use
BitcoinTX** first (off by default), and keep BitcoinTX open while you use
the AI. The same section turns access off again or resets the key (the
server picks up a new key by itself). `BTCTX_MCP_FILE` points at another
file.

**Docker, StartOS, or from source:** in BitcoinTX, **Settings → Connect an
AI Assistant**, turn on **Let AI assistants use BitcoinTX** and click
**Create AI key** (it's shown once; **New key** replaces it, **Revoke**
deletes it).

| Variable | Meaning |
|----------|---------|
| `BTCTX_URL` | Where BitcoinTX is reachable: Docker the host and port you published, e.g. `http://localhost:8080` (from another machine, an `https://` address: over plain `http://` the key and your ledger cross the network unencrypted, and the connector warns in its log); StartOS the **MCP API** address from the service's Interfaces (`https://….local/api`; the **Connect an AI Assistant** action shows it with a ready-made config); from source `http://localhost:8000` |
| `BTCTX_AI_KEY` | The AI key. Put it in the configuration file, not in a chat or a shell command (which stays in the history) |
| `BTCTX_VERIFY_TLS` | `false` to accept a self-signed certificate (StartOS `.local` addresses) |
| `BTCTX_CA_BUNDLE` | Or: path to the CA certificate that signed it (StartOS lets you download its root CA). Safer than disabling verification |

`BTCTX_USERNAME` and `BTCTX_PASSWORD` are no longer used. While
`BTCTX_PASSWORD` is set, every tool answers with how to switch to a key and
sends nothing; after switching, change your BitcoinTX password, since the old
one sat in that file.

### Claude Desktop

Settings → Developer → Edit Config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "bitcointx": {
      "command": "btctx-mcp",
      "env": {
        "BTCTX_URL": "http://localhost:8080",
        "BTCTX_AI_KEY": "YOUR_BITCOINTX_AI_KEY"
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
  -e BTCTX_URL=http://localhost:8080 -e BTCTX_AI_KEY=YOUR_BITCOINTX_AI_KEY \
  -- btctx-mcp
```

Then paste your key over the placeholder in `~/.claude.json`
(`mcpServers.bitcointx.env`), so it never goes into your shell history.

## Using it

> Here's my River email: "You bought 0.00231 BTC for $150.00 (fee $1.49) on Mar 3"

> I withdrew everything from River to my Trezor on March 10, network fee 1,800 sats

> Got paid 250k sats for a logo design on 2024-05-02, went straight to cold storage

The assistant asks when something tax-relevant is ambiguous (is that address
your own wallet or someone else's? bank-funded or from your River cash
balance?), previews, then saves once you confirm. Your AI client will also ask
you to approve each tool call unless you tell it not to.

## Security notes

- **What the AI key can do:** read the ledger, add, change or delete single
  transactions, recalculate, and make a backup copy on the server
  (`backup_ledger`). Only while AI access is on.
- **What it can't do** (BitcoinTX answers 403): log in, change your username
  or password, create or revoke keys, turn AI access on or off, restore or
  download a backup, export or import files, delete everything, apply Ledger
  Review fixes, change settings, or open reports.
- Mac app: the key sits in `mcp.json`, readable only by you, and works only
  from this computer. Settings → Connect an AI Assistant turns access off or
  resets the key.
- Docker/StartOS: the key sits in your AI app's configuration on your
  computer; anyone who can read that file can do what the key allows. Revoke
  it or make a new one in Settings → Connect an AI Assistant. BitcoinTX stores
  only a hash of it, and restoring a backup never brings back an old key.
- With a cloud AI, what the tools return goes to the provider (see
  [Privacy](https://github.com/DigiMonk73/BTCTX-MCP/blob/main/mcp_server/README.md#privacy-cloud-or-local-model)).
- There is no bulk delete, and every write is visible in BitcoinTX. Before a
  large import, have the AI run `backup_ledger` or take a backup yourself
  (Settings → Backup & Restore, or `scripts/backup-db.sh` on a server).

## Development

```bash
# from the repo root
pip install -r backend/requirements.txt -r requirements-dev.txt ./mcp_server
mkdir -p frontend/dist
pytest mcp_server/tests backend/tests/test_entry_import.py
```

The tests run an MCP client against this server, which calls the real FastAPI
app in-process on a temporary database. Price lookups are stubbed.
