# BitcoinTX (with MCP) – Bitcoin Portfolio & Tax Tracker

A self-hosted Bitcoin portfolio tracker and tax report generator, forked from
[BitcoinTX-org/BTCTX](https://github.com/BitcoinTX-org/BTCTX). This fork adds an
**MCP server** so an AI assistant can enter transactions for you, plus the
tax and security fixes listed in [docs/CHANGELOG.md](docs/CHANGELOG.md).

It tracks BTC and USD balances with **double-entry accounting**, computes
FIFO cost basis and capital gains per account, and prints IRS **Form 8949**
and **Schedule D**, including the Form 1099-DA boxes that start with tax year 2025.

<img width="1000" alt="Dashboard" src="docs/images/dashboard.png" />

## Features

- **Dashboard**: BTC holdings, USD balance, realized and unrealized gains
- **Transactions**: Deposit, Withdrawal, Transfer, Buy and Sell. Every edit
  recalculates the whole ledger, so backdated entries come out right.
- **FIFO lots per account**: a transfer keeps each lot's acquisition date and basis
- **Reports**: Form 8949 and Schedule D (filled, flattened PDFs), a complete
  tax report, and transaction history (PDF/CSV). When your broker's 1099-DA
  says something different for a sale, record that on the transaction and the
  right Form 8949 box follows.
- **Imports**: River CSV export, generic CSV, and the AI route below
- **AI entry (MCP)**: paste an exchange email or a wallet history, or type
  "moved 0.05 BTC to my Coldcard yesterday, fee 2k sats". The assistant
  previews the rows (duplicate check, fair market value, resulting gains) and
  saves them once you confirm.
- **Tax timezone** (Settings): decides which tax year a late-night Dec 31
  transaction lands in, the dates on Form 8949, and when a lot turns long-term
- **Encrypted backup/restore**, single-user login

## Install

### macOS app

```bash
./desktop/build-mac.sh      # builds desktop/dist/BitcoinTX.app
```

See [docs/MACOS_DESKTOP_APP.md](docs/MACOS_DESKTOP_APP.md). The app keeps its
data in `~/Library/Application Support/BitcoinTX`. While it's open it serves
its window from `http://127.0.0.1:8765`, which is also the address the MCP
server uses.

### Docker

```bash
docker build -t btctx .
docker run -d -p 8080:80 -v btctx-data:/data btctx
# open http://localhost:8080
```

StartOS packaging: [docs/STARTOS_COMPATIBILITY.md](docs/STARTOS_COMPATIBILITY.md).

### From source

Requires Python 3.10+ and Node.js 20+.

```bash
pip install -r backend/requirements.txt
(cd frontend && npm ci && npm run build)
uvicorn backend.main:app --port 8000     # open http://localhost:8000
```

A `.env` file is optional; see [.env.example](.env.example).

### First login

A fresh install starts with the account `admin` / `password`. The first
screen lets you claim it with your own username and password. Do that before
you expose the app on a network.

## Connect an AI (MCP)

In BitcoinTX, open **Settings → Connect an AI Assistant**, copy the setup
prompt and paste it into your AI app (Claude Code, Claude Desktop, Grok Build
or any app that runs MCP servers on your computer). The AI sets itself up
following [mcp_server/AI_SETUP.md](mcp_server/AI_SETUP.md); you type your
password into its configuration yourself. Or by hand:

```bash
pip install "git+https://github.com/DigiMonk73/BTCTX-MCP.git#subdirectory=mcp_server"
claude mcp add bitcointx -e BTCTX_URL=http://127.0.0.1:8765 \
  -e BTCTX_USERNAME=you -e BTCTX_PASSWORD=your-password -- btctx-mcp
```

[mcp_server/README.md](mcp_server/README.md) covers the Claude Desktop
config, Docker and StartOS addresses, TLS options, and example prompts.

## Upgrading from BitcoinTX v0.7 or earlier

1. Download an encrypted backup (Settings → Backup & Restore).
2. Start the new version. It upgrades the database automatically and keeps a
   copy of the old one in a `backups` folder next to it.
3. Click **Settings → Recalculate Ledger** once.
4. Check your **Tax Timezone** in Settings.

This release changes how transfer fees, sale proceeds and the one-year
holding period are calculated, so gains stored by older versions can change.

## Yearly IRS forms

`python scripts/irs_new_year.py 2026` downloads the year's final Form 8949
and Schedule D, checks every field the app fills, and runs the form tests. A
scheduled GitHub workflow flags when new forms are published. See
[docs/IRS_ANNUAL_FORM_UPDATE.md](docs/IRS_ANNUAL_FORM_UPDATE.md).

## Development

```bash
pip install -r backend/requirements.txt -r requirements-dev.txt ./mcp_server
make hooks        # pre-push gate: lint, static checks, fast tests, smoke test
make test         # full hermetic suite (temp DB, stubbed prices, no network)
make check        # everything CI runs except the Docker/macOS builds
```

Testing guide: [docs/TESTING.md](docs/TESTING.md). Architecture and
conventions: [CLAUDE.md](CLAUDE.md).

| Layer | Tech |
|---|---|
| Frontend | React + TypeScript + Vite |
| Backend | FastAPI + SQLAlchemy + SQLite |
| PDFs | pypdf (IRS form filling), ReportLab (reports) |
| BTC prices | CoinGecko, Kraken, CoinDesk (fallback chain) |
| AI | MCP server (Python `mcp` SDK, stdio) |

BitcoinTX doesn't give tax advice. Check its output before you file.

## License

MIT, see [LICENSE](LICENSE).
