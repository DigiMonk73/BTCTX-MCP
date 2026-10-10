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
#   --fresh        empty the test folder first (refused while a test run is open)
#   --background   start it detached and return; its output goes to <folder>/logs/
#
# The folder is $BTCTX_TEST_DATA_DIR, else btctx-test-build in the user's
# temp folder. The script uses only a folder that is empty or that it marked
# as its own, and never the installed app's folder however it is spelled. An
# MCP server reaches the test run with BTCTX_MCP_FILE=<folder>/mcp.json in
# the server's own environment (the MCP Inspector's -e, a client's "env" block).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="$ROOT/desktop/dist/BitcoinTX.app"
TEMP="${TMPDIR:-$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null || echo /tmp)}"
DATA="${BTCTX_TEST_DATA_DIR:-$TEMP/btctx-test-build}"
PORT=8766
MARKER=".btctx-test-folder"
# What the app keeps in its data folder (desktop/desktop_paths.py), for --fresh
APP_FILES=(btctx.db btctx.db-journal btctx.db-wal btctx.db-shm .btctx_secret_key mcp.json setup-code.txt
           backups logs irs-draft-forms)

fail() { echo "run-test-build.sh: $*" >&2; exit 1; }

# A path as it is on disk (symlinks resolved, the case stored on disk),
# without creating it: the deepest existing folder resolved, the rest appended.
physical() {
  local path="$1" rest=""
  case "$path" in /*) ;; *) path="$PWD/$path" ;; esac
  while [ ! -d "$path" ]; do
    rest="/$(basename "$path")$rest"
    path="$(dirname "$path")"
  done
  echo "$(cd "$path" && /bin/pwd -P)$rest"
}

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# Whether $1 is the installed app's folder or inside it: by name, ignoring
# case (macOS file systems do), and by identity for each existing folder on
# the way up, so a symlink or another spelling is caught too.
in_real_folder() {
  local d="$1" real="$HOME/Library/Application Support/BitcoinTX" name
  for name in "$real" "$(physical "$real")"; do
    case "$(lower "$d")/" in "$(lower "$name")/"*) return 0 ;; esac
  done
  [ -e "$real" ] || return 1
  while [ -n "$d" ] && [ "$d" != "/" ]; do
    if [ -e "$d" ] && [ "$d" -ef "$real" ]; then return 0; fi
    d="$(dirname "$d")"
  done
  return 1
}

fresh=0
background=0
where=0
while [ $# -gt 0 ]; do
  case "$1" in
    --app) APP="${2:?--app needs a path}"; shift 2 ;;
    --fresh) fresh=1; shift ;;
    --background) background=1; shift ;;
    --where) where=1; shift ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) echo "run-test-build.sh: unknown option $1 (--help)" >&2; exit 2 ;;
  esac
done

[ -n "${HOME:-}" ] || fail "HOME is not set"
DATA="$(physical "$DATA")"
in_real_folder "$DATA" && fail "refusing $DATA: it is the installed app's data folder"
if [ -d "$DATA" ] && [ ! -e "$DATA/$MARKER" ] && [ -n "$(ls -A "$DATA")" ]; then
  fail "refusing $DATA: it isn't empty and isn't a test folder this script made"
fi
mkdir -p "$DATA"
touch "$DATA/$MARKER"
if [ "$where" = 1 ]; then
  echo "$DATA"
  exit 0
fi

BIN="$APP/Contents/MacOS/BitcoinTX"
[ -x "$BIN" ] || fail "no app at $APP (build one with desktop/build-mac.sh, or give --app)"
if [ "$fresh" = 1 ]; then
  if curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/api/health"; then
    fail "a BitcoinTX still answers on port $PORT: quit it before --fresh"
  fi
  for name in "${APP_FILES[@]}"; do rm -rf "${DATA:?}/$name"; done
fi

export BTCTX_DESKTOP_DATA_DIR="$DATA" BTCTX_DESKTOP_PORT="$PORT"
echo "BitcoinTX test run: data $DATA, http://127.0.0.1:$PORT"
if [ "$background" = 1 ]; then
  mkdir -p "$DATA/logs"
  nohup "$BIN" >>"$DATA/logs/run-test-build.out" 2>&1 &
  echo "started, pid $!"
else
  exec "$BIN"
fi
