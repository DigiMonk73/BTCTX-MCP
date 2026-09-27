# BitcoinTX Desktop App (macOS)

Build configuration for the macOS app (PyInstaller + pywebview). Full details:
[docs/MACOS_DESKTOP_APP.md](../docs/MACOS_DESKTOP_APP.md).

Prebuilt `BitcoinTX-macOS.dmg` and `.zip` downloads are on the
[releases page](https://github.com/DigiMonk73/BTCTX-MCP/releases/latest);
this folder is for building it yourself.

## Prerequisites

- macOS
- Python 3.10+ (e.g. `brew install python@3.11`)
- Node.js with npm (CI uses Node 22)

Nothing else: IRS forms are filled in pure Python (pypdf).

## Build

```bash
# From the project root
./desktop/build-mac.sh
```

Creates `desktop/.venv`, installs `backend/requirements.txt` and
`desktop/requirements.txt`, builds the frontend, and runs PyInstaller.
Output: `desktop/dist/BitcoinTX.app` (plus `BitcoinTX.dmg` if `create-dmg`
is installed).

```bash
open desktop/dist/BitcoinTX.app
```

## Runtime

- Serves on `http://127.0.0.1:8765` (override with `BTCTX_DESKTOP_PORT`). If
  another program holds the port, a dialog offers Retry, Use Another Port
  (this session only) or Quit.
- Data: `~/Library/Application Support/BitcoinTX/`: `btctx.db`, the
  per-install session key `.btctx_secret_key`, `mcp.json` (the AI
  key) and `backups/`.
- Log: `~/Library/Logs/BitcoinTX/BitcoinTX.log`.
- MCP server: needs no settings; it reads `mcp.json`. Turn on **Settings →
  Connect an AI Assistant → Let AI assistants use BitcoinTX** first (off by
  default). Setup: the same section, or [mcp_server/README.md](../mcp_server/README.md).

## Troubleshooting

- **Won't open (Gatekeeper):** right-click → Open; on macOS 15 or later open
  it once, then **System Settings → Privacy & Security → Open Anyway**. Or
  `xattr -cr /path/to/BitcoinTX.app`.
- **Backend fails to start / blank window:** read
  `~/Library/Logs/BitcoinTX/BitcoinTX.log`, or run
  `desktop/dist/BitcoinTX.app/Contents/MacOS/BitcoinTX` in Terminal to see the
  log live. After adding a backend module, check it's in `hiddenimports` in
  `BitcoinTX.spec`.

## Files

| File | Purpose |
|------|---------|
| `entrypoint.py` | Launcher: sets data paths, starts Uvicorn, opens the pywebview window |
| `desktop_ports.py` | Fixed-port binding, retry and the port-busy dialog |
| `BitcoinTX.spec` | PyInstaller configuration (hidden imports, bundle version) |
| `build-mac.sh` | Build script |
| `requirements.txt` | Desktop-only packages (pyinstaller, pywebview) |
| `resources/icon.icns` | App icon |
