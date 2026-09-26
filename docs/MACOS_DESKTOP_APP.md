# macOS Desktop App

BitcoinTX can be packaged as a standalone macOS app with **PyInstaller** and
**pywebview**. The `.app` bundles the FastAPI backend, the built React frontend
and a Python runtime, so end users need nothing else installed. IRS Form 8949 /
Schedule D are filled in pure Python (pypdf), so there are no extra system
tools to install either.

Quick start for building: [desktop/README.md](../desktop/README.md).

## How it works

```
BitcoinTX.app
   └─ desktop/entrypoint.py
        ├─ sets DATABASE_FILE=~/Library/Application Support/BitcoinTX/btctx.db
        ├─ sets BTCTX_FRONTEND_DIST to the bundled frontend/dist (bundled app only)
        ├─ if a BitcoinTX already answers /api/health on 8765: brings it forward, exits
        ├─ binds 127.0.0.1:8765 (SO_REUSEADDR, retried up to 10s; desktop/desktop_ports.py)
        ├─ starts Uvicorn (backend.main:app) on that socket in a daemon thread
        ├─ polls http://127.0.0.1:<port>/ until it answers (backoff 0.1s → 1s, 30s timeout)
        └─ opens a pywebview (WebKit) window on that URL
```

- **Port:** fixed at `127.0.0.1:8765` so external clients (e.g. the MCP
  server) can find the app. Override with the `BTCTX_DESKTOP_PORT` environment
  variable. The listening socket itself is bound (with `SO_REUSEADDR`, like
  Uvicorn) and passed to Uvicorn, so connections left in TIME_WAIT by the
  previous run don't block it (the v0.9.1 bug: a probe without
  `SO_REUSEADDR` said "busy" and the app silently took a random port). If
  another program really holds the port for 10 seconds, a dialog offers
  Retry, Use Another Port (this session only; a banner says AI assistants
  can't connect) or Quit. It never switches ports silently.
- **One copy:** a second launch finds the first on the port, brings it
  forward and exits instead of starting a second backend.
- **Log file:** `~/Library/Logs/BitcoinTX/BitcoinTX.log` (rotating, 1 MB × 3),
  including every port decision and its errno.
- **Localhost only:** the server binds to `127.0.0.1`, never to the network.
- **Native save dialog:** `entrypoint.py` exposes a `DesktopAPI.save_file()`
  method to JavaScript via pywebview's `js_api`. The frontend
  (`frontend/src/utils/desktopDownload.ts`) uses it for PDF, CSV and `.btx`
  backup downloads, because WebKit in pywebview doesn't handle browser downloads.

## Data and secrets

Everything lives in `~/Library/Application Support/BitcoinTX/`:

| File | What it is |
|------|------------|
| `btctx.db` | SQLite database (all your data) |
| `.btctx_secret_key` | Per-install session signing key, generated on first launch, mode 600 |
| `backups/` | Copies of `btctx.db` taken automatically before a schema upgrade or a restore (mode 600) |

A new app version upgrades the database schema on first launch (after copying
it into `backups/`). Opening an older app version on a database a newer one
already upgraded is refused with an error instead of risking your data.

The desktop app does not hardcode a secret key. `backend/secret_key.py` uses
`SECRET_KEY` from the environment if set (and not a known public default),
otherwise generates a random key once and stores it next to the database.
Deleting the key file only logs everyone out; a new one is generated.

```bash
open ~/Library/Application\ Support/BitcoinTX/            # open in Finder
sqlite3 ~/Library/Application\ Support/BitcoinTX/btctx.db  # inspect
```

**Backups:** use the encrypted backup/restore in the app's Settings page, or
quit the app and copy the whole `BitcoinTX` folder.

## Building

Requirements: macOS, Python 3.10+, Node.js with npm (CI builds with Node 22).

```bash
./desktop/build-mac.sh
```

The script:

1. Finds a Python 3.10+ interpreter (`python3.13` … `python3.10`, `python3`)
2. Creates/reuses `desktop/.venv` and installs `backend/requirements.txt` plus
   `desktop/requirements.txt` (PyInstaller, pywebview)
3. Builds the frontend (`npm ci && npm run build` in `frontend/`)
4. Checks `desktop/resources/icon.icns` (warns if missing) and
   `backend/assets/irs_templates/` (fails if missing)
5. Runs `pyinstaller --clean --noconfirm BitcoinTX.spec`
6. Creates `desktop/dist/BitcoinTX.dmg` if `create-dmg` is installed
   (`brew install create-dmg`)

Output: `desktop/dist/BitcoinTX.app`. Test with `open desktop/dist/BitcoinTX.app`.

### Manual build

```bash
cd desktop
python3 -m venv .venv && source .venv/bin/activate
pip install -r ../backend/requirements.txt -r requirements.txt
(cd ../frontend && npm ci && npm run build)
pyinstaller --clean --noconfirm BitcoinTX.spec
```

### Run without bundling

With the venv active and `frontend/dist` built, from the repo root:

```bash
PYTHONPATH=. python desktop/entrypoint.py
```

(`PYTHONPATH=.` is needed so Uvicorn can import `backend.main`.)

In this mode the backend serves `frontend/dist` from the repo and still uses
the Application Support database.

## BitcoinTX.spec

- **Datas:** the whole `backend/` package (including `assets/irs_templates/`)
  and `frontend/dist/`.
- **Hidden imports:** FastAPI/Starlette/Uvicorn internals, pydantic,
  SQLAlchemy SQLite dialect, httpx, bcrypt, cryptography, pypdf, reportlab,
  tzdata, pywebview, and the `backend.*` router/service/model modules.
  **When you add a backend module or a dependency, add it here** or the bundled
  app may fail at import time even though dev runs work.
- **Excludes:** pytest, tkinter, matplotlib, numpy, scipy, pandas.
- **Bundle:** `org.bitcointx.desktop`, version `0.9.1` (`CFBundleVersion` /
  `CFBundleShortVersionString`; bump both on release), minimum macOS 10.15,
  dark mode supported.

## Using the MCP server with the Mac app

**Settings → Connect an AI Assistant** in the app has a setup prompt to paste
into your AI app and one-line commands with no password, username or port.
At startup the backend writes `~/Library/Application Support/BitcoinTX/mcp.json`
(0600, in a 0700 folder): the app's URL, port, pid, version and an **AI
assistant key** (`backend/services/mcp_key.py`). The MCP server reads it and
sends the key as `Authorization: Bearer …`. Only a SHA-256 of the key is in the
database (`app_settings`); the key stays the same across restarts and after a
restore. It's accepted only from 127.0.0.1, only while AI access is on, and
never for backup/restore, CSV import, delete-all or the key settings
themselves. Settings can turn access off or reset the key. The app must be
running while the AI uses it. See [mcp_server/README.md](../mcp_server/README.md).

## CI

On every branch push (or manually from the Actions tab), `.github/workflows/ci.yml`
runs `./desktop/build-mac.sh` on `macos-latest`, launches the bundled binary,
checks it answers on `http://127.0.0.1:8765/` and that
`/api/import/entries/preview` returns 401 without a login, then uploads the
zipped `.app` as a build artifact.

Releases (`.github/workflows/release.yml`, on a `release/vX.Y.Z` branch) build
the app the same way and attach `BitcoinTX-macOS.dmg` (made with `hdiutil`,
drag-to-Applications) and `BitcoinTX-macOS.zip` to the GitHub release. Both
are unsigned and not notarized.

## Troubleshooting

**App won't open (Gatekeeper).** The app is unsigned. The first time,
right-click (Control-click) it in Applications and choose **Open**. On macOS 15
or later that no longer offers Open: try to open it once, then go to
**System Settings → Privacy & Security** and click **Open Anyway**. Or clear
the quarantine flag:
```bash
xattr -cr /path/to/BitcoinTX.app
```

**Crashes or blank window.** Read `~/Library/Logs/BitcoinTX/BitcoinTX.log`, or
run the binary from Terminal to see the same output:
```bash
/path/to/BitcoinTX.app/Contents/MacOS/BitcoinTX
```
If the backend doesn't answer within 30 seconds the app logs
"Backend failed to start" and exits. A missing hidden import in
`BitcoinTX.spec` is the usual cause after adding a module.

**MCP client can't connect.** If the app shows the "running on port N this
session" banner, another program had port 8765 when it started: quit
BitcoinTX, close that program (`lsof -nP -iTCP:8765 -sTCP:LISTEN` names it) and
reopen. The log records each attempt ("Port 8765 unavailable … EADDRINUSE").

**Debugging PyInstaller:** `pyinstaller --debug=imports BitcoinTX.spec`.

## App icon

`desktop/resources/icon.icns` is checked in. To regenerate it from a
1024×1024 PNG:

```bash
mkdir icon.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s icon.png --out icon.iconset/icon_${s}x${s}.png
  sips -z $((s*2)) $((s*2)) icon.png --out icon.iconset/icon_${s}x${s}@2x.png
done
iconutil -c icns icon.iconset -o desktop/resources/icon.icns
```
