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

Creates `desktop/.venv`, installs the locks `backend/requirements.txt` and
`desktop/requirements.txt` (hashes checked), builds the frontend, and runs
PyInstaller.
Output: `desktop/dist/BitcoinTX.app` (plus `BitcoinTX.dmg` if `create-dmg`
is installed).

To try the build on a Mac where BitcoinTX is installed, never `open` it
or run its binary by itself: that opens the real ledger. Use the script, for
every launch: it runs the build on its own test folder and port 8766
(details, and the MCP server: [MACOS_DESKTOP_APP.md, "Testing a build"](../docs/MACOS_DESKTOP_APP.md#testing-a-build)).

```bash
desktop/run-test-build.sh            # --fresh: empty folder; --app PATH: another build
```

## Runtime

- Serves on `http://127.0.0.1:8765` (override with `BTCTX_DESKTOP_PORT`). If
  another program holds the port, a dialog offers Retry, Use Another Port
  (this session only) or Quit.
- Data: `~/Library/Application Support/BitcoinTX/`: `btctx.db`, the
  per-install session key `.btctx_secret_key`, `mcp.json` (the AI
  key) and `backups/`. `BTCTX_DESKTOP_DATA_DIR` puts them (and the log, in
  `logs/`) in another folder, for testing (`run-test-build.sh`).
- Log: `~/Library/Logs/BitcoinTX/BitcoinTX.log`.
- MCP server: needs no settings with the installed app; it reads `mcp.json`. Turn on **Settings →
  Connect an AI Assistant → Let AI assistants use BitcoinTX** first (off by
  default). Setup: the same section, or [mcp_server/README.md](../mcp_server/README.md).

## Troubleshooting

- **Won't open (Gatekeeper):** right-click → Open; on macOS 15 or later open
  it once, then **System Settings → Privacy & Security → Open Anyway**. Or
  `xattr -cr /path/to/BitcoinTX.app`.
- **Backend fails to start / blank window:** read
  `~/Library/Logs/BitcoinTX/BitcoinTX.log`, or run the build in Terminal
  with `desktop/run-test-build.sh` to see the log live. After adding a
  backend module, check it's in `hiddenimports` in `BitcoinTX.spec`.

## Files

| File | Purpose |
|------|---------|
| `entrypoint.py` | Launcher: sets data paths, starts Uvicorn, opens the pywebview window |
| `desktop_ports.py` | Fixed-port binding, retry and the port-busy dialog |
| `desktop_paths.py` | The data and log folders (`BTCTX_DESKTOP_DATA_DIR` for a test run) |
| `run-test-build.sh` | Runs a build on a test folder and port 8766, never the real ledger |
| `BitcoinTX.spec` | PyInstaller configuration (hidden imports, bundle version) |
| `build-mac.sh` | Build script |
| `requirements.in` | Desktop-only packages (pyinstaller, pywebview, and setuptools to build proxy-tools), pinned |
| `requirements.txt` | Their lock, with hashes (`make lock`; docs/MAINTENANCE.md) |
| `resources/icon.icns` | App icon |
