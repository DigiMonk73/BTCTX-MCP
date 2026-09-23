# BitcoinTX Desktop App (macOS)

Build configuration for the macOS app (PyInstaller + pywebview). Full details:
[docs/MACOS_DESKTOP_APP.md](../docs/MACOS_DESKTOP_APP.md).

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

- Serves on `http://127.0.0.1:8765` (override with `BTCTX_DESKTOP_PORT`; falls
  back to a random port if 8765 is taken).
- Data: `~/Library/Application Support/BitcoinTX/btctx.db`, with the
  per-install session key `.btctx_secret_key` beside it.
- MCP server: set `BTCTX_URL=http://127.0.0.1:8765`; see
  [mcp_server/README.md](../mcp_server/README.md).

## Troubleshooting

- **Won't open (Gatekeeper):** right-click → Open, or
  `xattr -cr desktop/dist/BitcoinTX.app`.
- **Backend fails to start / blank window:** run
  `desktop/dist/BitcoinTX.app/Contents/MacOS/BitcoinTX` in Terminal to see the
  log. After adding a backend module, check it's in `hiddenimports` in
  `BitcoinTX.spec`.

## Files

| File | Purpose |
|------|---------|
| `entrypoint.py` | Launcher: sets data paths, starts Uvicorn, opens the pywebview window |
| `BitcoinTX.spec` | PyInstaller configuration (hidden imports, bundle version) |
| `build-mac.sh` | Build script |
| `requirements.txt` | Desktop-only packages (pyinstaller, pywebview) |
| `resources/icon.icns` | App icon |
