#!/usr/bin/env bash
# Run a Mac app build for testing on its own data folder and port 8766, never
# on the installed app's real ledger (~/Library/Application Support/BitcoinTX).
# Every launch uses the same folder, from any shell, so a reopen or a second
# launch finds the same data: run this script for each one, never the app's
# binary by itself (that opens the real ledger).
#
#   desktop/run-test-build.sh [--app PATH] [--fresh] [--background]
#   desktop/run-test-build.sh --where       # print the folder (mcp.json is in it)
#
#   --app PATH     the build to run (default: desktop/dist/BitcoinTX.app)
#   --fresh        empty the test folder first
#   --background   start it detached and return; its log is in <folder>/logs/
#
# The folder is $BTCTX_TEST_DATA_DIR, else $TMPDIR/btctx-test-build. An MCP
# server reaches the test run with BTCTX_MCP_FILE=<folder>/mcp.json in the
# server's own environment (the MCP Inspector's -e, a client's "env" block).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/desktop/dist/BitcoinTX.app"
DATA="${BTCTX_TEST_DATA_DIR:-${TMPDIR:-/tmp}/btctx-test-build}"
PORT=8766
# What the app keeps in its data folder (desktop/desktop_paths.py), for --fresh
APP_FILES=(btctx.db btctx.db-journal btctx.db-wal btctx.db-shm .btctx_secret_key mcp.json setup-code.txt
           backups logs irs-draft-forms)

fresh=0
background=0
where=0
while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP="${2:?--app needs a path}"; shift 2 ;;
    --fresh) fresh=1; shift ;;
    --background) background=1; shift ;;
    --where) where=1; shift ;;
    -h|--help) sed -n '2,17p' "$0"; exit 0 ;;
    *) echo "run-test-build.sh: unknown option $1 (--help)" >&2; exit 2 ;;
  esac
done

mkdir -p "$DATA"
DATA="$(cd "$DATA" && pwd -P)"
REAL="$(cd "$HOME" && pwd -P)/Library/Application Support/BitcoinTX"
case "$DATA/" in
  "$REAL/"*)
    echo "run-test-build.sh: refusing $DATA: it is the installed app's data folder" >&2
    exit 1 ;;
esac
if [ "$where" = 1 ]; then
  echo "$DATA"
  exit 0
fi

BIN="$APP/Contents/MacOS/BitcoinTX"
if [ ! -x "$BIN" ]; then
  echo "run-test-build.sh: no app at $APP (build one with desktop/build-mac.sh, or give --app)" >&2
  exit 1
fi
if [ "$fresh" = 1 ]; then
  for name in "${APP_FILES[@]}"; do rm -rf "${DATA:?}/$name"; done
fi

export BTCTX_DESKTOP_DATA_DIR="$DATA" BTCTX_DESKTOP_PORT="$PORT"
echo "BitcoinTX test run: data $DATA, http://127.0.0.1:$PORT"
if [ "$background" = 1 ]; then
  nohup "$BIN" >/dev/null 2>&1 &
  echo "started, pid $!"
else
  exec "$BIN"
fi
