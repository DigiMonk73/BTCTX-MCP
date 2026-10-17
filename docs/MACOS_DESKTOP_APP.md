# macOS Desktop App

BitcoinTX can be packaged as a standalone macOS app with **PyInstaller** and
**pywebview**. The `.app` bundles the FastAPI backend, the built React frontend
and a Python runtime, so end users need nothing else installed. IRS Form 8949 /
Schedule D are filled in pure Python (pypdf), so there are no extra system
tools to install either.

Each GitHub release has a ready-made `BitcoinTX-macOS.dmg` and `.zip`
(unsigned; see Troubleshooting). Build it yourself only to run unreleased code.
Quick start for building: [desktop/README.md](../desktop/README.md).

## Checking a download

The app isn't signed by Apple, so macOS can't say who made it; the release
can. Its `SHA256SUMS` holds the SHA-256 of each file, and GitHub keeps a
signed build provenance attestation of each, made by the release workflow.
Save `SHA256SUMS` next to the `.dmg` and, in that folder, before opening
the app (check the `.dmg`: Safari unzips a downloaded `.zip` by itself):

```bash
shasum -a 256 -c --ignore-missing SHA256SUMS   # BitcoinTX-macOS.dmg: OK
gh attestation verify BitcoinTX-macOS.dmg -R DigiMonk73/BTCTX-MCP \
  --signer-workflow DigiMonk73/BTCTX-MCP/.github/workflows/release.yml
```

The first says the file is the one the release lists (`--ignore-missing`
leaves out the release's other files, the ones you didn't download); the
second (the GitHub CLI, signed in) that this repository's release workflow
built it. If either reports a mismatch, don't open it: download it again
from the release page.

## How it works

```
BitcoinTX.app
   └─ desktop/entrypoint.py
        ├─ sets DATABASE_FILE=~/Library/Application Support/BitcoinTX/btctx.db
        │    (or in BTCTX_DESKTOP_DATA_DIR, for a test run; desktop/desktop_paths.py)
        ├─ sets BTCTX_FRONTEND_DIST to the bundled frontend/dist (bundled app only)
        ├─ if a BitcoinTX already answers /api/health on 8765: brings it forward
        │    (a test run only says so), exits
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
  forward (a test run only says "already open", see "Testing a build") and
  exits instead of starting a second backend.
- **Log file:** `~/Library/Logs/BitcoinTX/BitcoinTX.log` (rotating, 1 MB × 3),
  including every port decision and its errno.
- **Localhost only:** the server binds to `127.0.0.1`, never to the network,
  and answers only requests addressed to `127.0.0.1`, `localhost` or `[::1]`
  (421 for any other `Host`: `backend/security_headers.py`,
  `LocalAddressOnlyMiddleware`). Uvicorn runs with `proxy_headers=False`, so
  a client's own `X-Forwarded-For` never passes for its address.
- **The window's API:** `entrypoint.py` gives the window `DesktopAPI`
  (`desktop/desktop_api.py`) through pywebview's `js_api`, as
  `window.pywebview.api`. Only the app's own window has it: a browser or
  another program reaching `127.0.0.1` doesn't.
  - `save_file()`: the native Save dialog. The frontend
    (`frontend/src/utils/desktopDownload.ts`) uses it for PDF, CSV and `.btx`
    backup downloads, because WebKit in pywebview doesn't handle browser
    downloads.
  - `setup_code()`: the first-run setup code ("First start" below), only
    while the window shows one of the app's own pages (pywebview gives the
    API to whatever page its window shows).

## First start

A new install has the login every BitcoinTX starts with (`admin` /
`password`). While the account has it, logging in with it and claiming it
need the one-time **setup code**, as on Docker
(`backend/services/first_run.py`), which only the Mac account that runs
BitcoinTX can read:

- The backend makes the code at startup and keeps it in `setup-code.txt` in
  the data folder (mode 600, in the 0700 folder), and deletes it once the
  login is changed. The Mac app never writes it to its log, which a
  problem report may attach.
- In the app's window, the Sign in page is replaced by **Choose your
  username and password**: a username, and a new password (12 or more
  characters) typed twice. The window supplies the code
  (`DesktopAPI.setup_code()`), and the page logs in with the default login
  and changes it to the chosen one (`PATCH /api/users/{id}`), so every
  transaction is kept (`frontend/src/utils/ownLogin.ts`). Then it opens the
  Dashboard, as a first login does. It appears whenever the login is still
  the default one, an older install's included.
- From a browser at `http://127.0.0.1:8765/`, `admin` / `password` is
  refused without the code typed in (from `setup-code.txt` in the data
  folder).

## Data and secrets

Everything lives in `~/Library/Application Support/BitcoinTX/`:

| File | What it is |
|------|------------|
| `btctx.db` | SQLite database (all your data) |
| `.btctx_secret_key` | Per-install session signing key, generated on first launch, mode 600 |
| `mcp.json` | The app's address and AI key for the MCP server, mode 600 |
| `setup-code.txt` | The one-time first-run setup code, mode 600, only while the login is still `admin` / `password` ("First start") |
| `btc-prices/` | The hourly BTC price history (one `YYYY.csv` per year, about 3 MB), downloaded once from Bitstamp when your price choice allows public price sites, each year checked against a fingerprint; deleting it only means it's downloaded again |
| `backups/` | Copies of `btctx.db` (mode 600): taken automatically before a schema upgrade or a restore (newest 5 kept), before Ledger Review's hourly prices are applied (newest 5 kept, apart), before every transaction is deleted, by Delete All or by Create account on a ledger with transactions (`btctx-before-delete-all-….db`, newest 5 kept, apart), and the AI copies: those the AI connector's `backup_ledger` asks for, and one before the AI key's first change in an hour, an edit, a deletion, a recalculation or an import holding an entry dated before the latest entry (newest 3 kept, plus, for a week, the oldest and the first copy of each day made before the AI changed anything that day) |

A new app version upgrades the database schema on first launch (after copying
it into `backups/`). Opening an older app version on a database a newer one
already upgraded is refused with an error instead of risking your data.

The desktop app does not hardcode a secret key. `backend/secret_key.py` uses
`SECRET_KEY` from the environment if set (and not a known public default or
shorter than 32 characters),
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

1. Finds a Python 3.10+ interpreter: the one `BTCTX_BUILD_PYTHON` names
   (CI passes the Python 3.13 it sets up), else the newest of `python3.13`
   … `python3.10`, `python3`. A `desktop/.venv` made earlier keeps its
   Python (the log says so): delete it to build with another
2. Creates/reuses `desktop/.venv` and installs the locks
   `backend/requirements.txt` plus `desktop/requirements.txt` (PyInstaller,
   pywebview), each package checked against its hash
3. Builds the frontend (`npm ci && npm run build` in `frontend/`)
4. Checks `desktop/resources/icon.icns` (warns if missing) and
   `backend/assets/irs_templates/` (fails if missing)
5. Runs `pyinstaller --clean --noconfirm BitcoinTX.spec`
6. Creates `desktop/dist/BitcoinTX.dmg` if `create-dmg` is installed
   (`brew install create-dmg`)

Output: `desktop/dist/BitcoinTX.app`.

### Testing a build

**On a Mac where BitcoinTX is installed, never `open` a build, and never
run its binary by itself:** either opens the real ledger in
`~/Library/Application Support/BitcoinTX/` (and its newer schema would lock
the installed app out). Run it with the script instead, for every launch:

```bash
desktop/run-test-build.sh                    # desktop/dist/BitcoinTX.app
desktop/run-test-build.sh --app PATH         # another build, e.g. a CI artifact
desktop/run-test-build.sh --fresh            # start again from an empty folder
desktop/run-test-build.sh --background       # detached (for an agent's shell)
```

It sets `BTCTX_DESKTOP_DATA_DIR` to one test folder (`btctx-test-build` in the
user's temp folder, or `$BTCTX_TEST_DATA_DIR`) and `BTCTX_DESKTOP_PORT` to
8766, the same on every launch from any shell, so a reopen or a second
launch finds the same data. It uses only a folder that is empty or that it
marked as its own (`.btctx-test-folder`), never the installed app's folder
however it is spelled; `--fresh` is refused while a test run answers on
8766. That folder holds everything the app would keep in Application
Support (`btctx.db`, the session key, `mcp.json`, `setup-code.txt`,
`btc-prices/`, `backups/`) and its log
(`logs/BitcoinTX.log`); the log line "Test data folder from
BTCTX_DESKTOP_DATA_DIR" confirms it's in use. The app also runs with
`HOME=<folder>/home`: a build older than `BTCTX_DESKTOP_DATA_DIR` (every
release up to 1.2.5) ignores the variable and keeps its data under
`~/Library/Application Support`, which is then inside the test folder
too.

- **MCP server:** it looks for the installed app's `mcp.json` unless
  `BTCTX_MCP_FILE=<folder>/mcp.json` (`desktop/run-test-build.sh --where`
  prints the folder) is in **the MCP server's own environment**: the MCP
  Inspector's `-e`, or a client's `env` block. Exported in a shell, it may
  not reach the server: the Inspector passes it only through `-e`.
- **A build from 1.2.8 on calls itself "BitcoinTX Test"** on a test run:
  the window title and its messages (a second launch, a busy port) say
  so. The menu bar, the Dock and the page inside the window still say
  BitcoinTX (the first two come from the bundle), and an older build run
  with `--app` says BitcoinTX everywhere. Whatever a message says during a
  test run, act only on the test copy, and leave the installed app alone.
- **A second launch** on the same port says "BitcoinTX Test is already
  open" but doesn't bring a window forward: AppleScript would find the
  installed app by name.

### Manual build

```bash
cd desktop
python3 -m venv .venv && source .venv/bin/activate
# then run step 2 of build-mac.sh (the setuptools extraction and the two installs)
(cd ../frontend && npm ci && npm run build)
pyinstaller --clean --noconfirm BitcoinTX.spec
```

### Run without bundling

With the venv active and `frontend/dist` built, from the repo root:

```bash
D="$(desktop/run-test-build.sh --where)" && \
  BTCTX_DESKTOP_DATA_DIR="$D" BTCTX_DESKTOP_PORT=8766 PYTHONPATH=. python desktop/entrypoint.py
```

(`PYTHONPATH=.` is needed so Uvicorn can import `backend.main`.) The
backend serves `frontend/dist` from the repo. Without `BTCTX_DESKTOP_DATA_DIR`
it would use the Application Support database, the real ledger on a Mac
with BitcoinTX installed: keep the `&&`, so a failed `--where` starts
nothing.

## BitcoinTX.spec

- **Datas:** the `backend/` package (including `assets/irs_templates/`),
  but not `backend/tests/` (tests, fixtures, test ledgers) nor what a dev
  run leaves there (a `*.db`, `backups/`, `setup-code.txt`, hidden files
  such as `.btctx_secret_key`); `frontend/dist/` and `VERSION`.
- **Hidden imports:** FastAPI/Starlette/Uvicorn internals, pydantic,
  SQLAlchemy SQLite dialect, httpx, bcrypt, cryptography, pypdf, reportlab,
  tzdata, pywebview, and the `backend.*` router/service/model modules.
  **When you add a backend module or a dependency, add it here** or the bundled
  app may fail at import time even though dev runs work.
- **Excludes:** pytest, tkinter, matplotlib, numpy, scipy, pandas.
- **Bundle:** `org.bitcointx.desktop`, version from `VERSION`
  (`CFBundleVersion` / `CFBundleShortVersionString`; bump both on release,
  `backend/tests/test_versions_agree.py` checks), minimum macOS 10.15,
  dark mode supported.

## Using the MCP server with the Mac app

**Settings → Connect an AI Assistant** in the app has a setup prompt to paste
into your AI app and one-line commands with no password, username or port.
At startup the backend writes `~/Library/Application Support/BitcoinTX/mcp.json`
(0600, in a 0700 folder): the app's URL, port, pid, version and the **AI
key** (`backend/services/ai_key.py`). The MCP server reads it and sends the
key as `Authorization: Bearer …`. Only a SHA-256 of the key is in the
database (`app_settings`). Every start writes a new key, so a key lasts one
run of the app; an AI app left open across a restart carries on by itself,
since the MCP server rereads the file when its key is refused. A restore
keeps the key in use. It's accepted only from 127.0.0.1, only while AI access is on (off
until the owner turns it on in Settings), and only on the routes the MCP
tools use (`AI_KEY_ROUTES`; login, backup/restore, imports, delete-all, the
key and switch settings and every other route answer 403). Settings can turn access off or reset the key. The app must be
running while the AI uses it. See [mcp_server/README.md](../mcp_server/README.md).

## CI

On every pull request, every push to `develop` or `main`, or manually from the Actions tab, `.github/workflows/ci.yml`
runs `./desktop/build-mac.sh` on `macos-latest` with the Python 3.13 the job
sets up (`BTCTX_BUILD_PYTHON`, #284). The Mac app runs 3.13 on purpose, the
newest in the test matrix, which tests it; Docker and StartOS run 3.11. It
never takes whichever Python the runner has. It launches the bundled binary,
checks it answers on `http://127.0.0.1:8765/` and that
`/api/import/entries/preview` returns 401 without a login, then uploads the
zipped `.app` as a build artifact.

Releases (`.github/workflows/release.yml`, on a `release/vX.Y.Z` branch) build
the app the same way and attach `BitcoinTX-macOS.dmg` (made with `hdiutil`,
drag-to-Applications) and `BitcoinTX-macOS.zip` to the GitHub release. Both
are unsigned and not notarized. Before it creates the release, the release
job writes `SHA256SUMS` for these two files and `btctx.s9pk` (uploaded with
them) and attests the three (`actions/attest-build-provenance`); see
"Checking a download" above.

## Troubleshooting

**App won't open (Gatekeeper).** The app is unsigned: check the download
first ("Checking a download" above). The first time,
right-click (Control-click) it in Applications and choose **Open**. On macOS 15
or later that no longer offers Open: try to open it once, then go to
**System Settings → Privacy & Security** and click **Open Anyway**. Or clear
the quarantine flag:
```bash
xattr -cr /path/to/BitcoinTX.app
```

**Crashes or blank window.** Read `~/Library/Logs/BitcoinTX/BitcoinTX.log`, or
run the installed app from Terminal to see the same output:
```bash
/Applications/BitcoinTX.app/Contents/MacOS/BitcoinTX
```
A build you made runs only through `desktop/run-test-build.sh`, whose output
shows in Terminal the same way.
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
