#!/usr/bin/env bash
# Run a Mac app build for testing on its own data folder and port 8766, never
# on the installed app's real ledger (~/Library/Application Support/BitcoinTX).
# Every launch uses the same folder, from any shell, so a reopen or a second
# launch finds the same data: run this script for each one, never the app's
# binary by itself (that opens the real ledger). It runs a copy of the build,
# in the folder, with a bundle id of its own: <the build's id>.test-build.
#
#   desktop/run-test-build.sh [--app PATH] [--fresh] [--background]
#   desktop/run-test-build.sh --where       # print the folder (mcp.json is in it)
#
#   --app PATH     the build to run (default: the one app in desktop/dist,
#                  BitcoinTX.app or a pre-release's BitcoinTX Preview.app); one
#                  older than this script also gets a test home (HOME=<folder>/home),
#                  so it can't reach the real ledger either
#   --fresh        empty the test folder first (refused while a test run is open)
#   --background   start it detached and return; its output goes to <folder>/logs/
#
# The folder is $BTCTX_TEST_DATA_DIR, else btctx-test-build in the user's
# temp folder. The script uses only a folder that is empty or that it marked
# as its own, and never an installed app's folder (BitcoinTX's, or BitcoinTX
# Preview's: a tester's copy of their ledger) however it is spelled. An
# MCP server reaches the test run with BTCTX_MCP_FILE=<folder>/mcp.json in
# the server's own environment (the MCP Inspector's -e, a client's "env" block).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP=""
TEMP="${TMPDIR:-$(getconf DARWIN_USER_TEMP_DIR 2>/dev/null || echo /tmp)}"
DATA="${BTCTX_TEST_DATA_DIR:-$TEMP/btctx-test-build}"
PORT=8766
MARKER=".btctx-test-folder"
COPY=""
PLISTBUDDY=/usr/libexec/PlistBuddy
# What the app keeps in its data folder (desktop/desktop_paths.py), for --fresh
APP_FILES=(btctx.db btctx.db-journal btctx.db-wal btctx.db-shm .btctx_secret_key mcp.json setup-code.txt
           backups logs irs-draft-forms home)

fail() { echo "run-test-build.sh: $*" >&2; exit 1; }

# A path as it is on disk (symlinks resolved, the case stored on disk),
# without creating it: the deepest existing folder resolved, the rest appended.
# The path may hold no "." or ".." (checked first): after a folder that
# doesn't exist yet, they would only be resolved once mkdir created it.
physical() {
  local path="$1" rest="" top
  case "$path" in /*) ;; *) path="$PWD/$path" ;; esac
  while [ ! -d "$path" ]; do
    rest="/${path##*/}$rest"
    path="${path%/*}"
    [ -n "$path" ] || path=/
  done
  top="$(cd "$path" && /bin/pwd -P)" || fail "can't open $path"
  echo "$top$rest"
}

lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# Whether $1 is an installed app's folder or inside it: by name, ignoring
# case (macOS file systems do), and by identity for each existing folder on
# the way up, so a symlink or another spelling is caught too.
in_real_folder() {
  local real
  for real in "$HOME/Library/Application Support/BitcoinTX" "$HOME/Library/Application Support/BitcoinTX Preview"; do
    in_folder "$1" "$real" && return 0
  done
  return 1
}

in_folder() {
  local d="$1" real="$2" name
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

# Never through a proxy set for the whole machine (#474): its answer isn't BitcoinTX's
answers() { curl -s --noproxy '*' -m 2 -o /dev/null "http://127.0.0.1:$PORT/api/health"; }

bundle_id() { "$PLISTBUDDY" -c "Print :CFBundleIdentifier" "$1/Contents/Info.plist" 2>/dev/null; }

# Whether a process runs from the test copies: one still starting doesn't
# answer yet, and making the copy anew would delete the bundle it runs from.
# The path goes to awk through its environment, so awk's own command line
# never holds it.
copy_runs() {
  ps -axo command= | RUNNING="$COPIES/" awk 'index($0, ENVIRON["RUNNING"]) > 0 { found = 1 } END { exit !found }'
}

# The build's copy, made anew for each launch nothing answers for: an
# unpacked build can be replaced at the same path. .source is written last,
# so a copy cut short is never taken for a whole one.
make_copy() {
  command -v ditto >/dev/null && command -v codesign >/dev/null && [ -x "$PLISTBUDDY" ] \
    || fail "a copy with its own bundle id needs macOS's ditto, PlistBuddy and codesign"
  local id
  id="$(bundle_id "$APP")" || id=""
  rm -rf "${COPIES:?}"
  mkdir -p "$COPIES"
  ditto --noqtn "$APP" "$COPY" || fail "can't copy $APP"
  if [ -n "$id" ]; then
    "$PLISTBUDDY" -c "Set :CFBundleIdentifier $id.test-build" "$COPY/Contents/Info.plist"
  else
    "$PLISTBUDDY" -c "Add :CFBundleIdentifier string org.bitcointx.desktop.test-build" "$COPY/Contents/Info.plist"
  fi || fail "can't give the copy its own bundle id"
  # The build's own nested code stays signed as it was; --deep only if it isn't
  { codesign --force --sign - "$COPY" && codesign --verify --deep --strict "$COPY"; } 2>/dev/null \
    || codesign --force --deep --sign - "$COPY" 2>/dev/null || fail "can't sign the copy of $APP"
  printf '%s\n' "$SOURCE" >"$COPIES/.source"
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
    -h|--help) sed -n '2,24p' "$0"; exit 0 ;;
    *) echo "run-test-build.sh: unknown option $1 (--help)" >&2; exit 2 ;;
  esac
done

# Refuses the installed app's folder, and a folder with other things in it:
# --fresh deletes the app's files there.
check_folder() {
  in_real_folder "$1" && fail "refusing $1: it is an installed app's data folder"
  local entries=""
  if [ -d "$1" ]; then
    entries="$(ls -A "$1")" || fail "can't list $1"
  fi
  if [ -n "$entries" ] && [ ! -e "$1/$MARKER" ]; then
    fail "refusing $1: it isn't empty and isn't a test folder this script made" \
      "(empty it, or set BTCTX_TEST_DATA_DIR to another folder)"
  fi
  return 0
}

[ -n "${HOME:-}" ] || fail "HOME is not set"
case "$DATA" in *[[:cntrl:]]*) fail "refusing a folder name with a control character (a newline...)" ;; esac
case "/$DATA/" in */./*|*/../*) fail "refusing $DATA: give the folder without . or .." ;; esac
DATA="$(physical "$DATA")"
check_folder "$DATA"
mkdir -p "$DATA"
# Created, it resolves again: it must still be the same folder, and allowed
[ "$(physical "$DATA")" = "$DATA" ] || fail "refusing $DATA: it resolves to $(physical "$DATA")"
check_folder "$DATA"
touch "$DATA/$MARKER"
COPIES="$DATA/test-app"
if [ "$where" = 1 ]; then
  echo "$DATA"
  exit 0
fi

if [ -z "$APP" ]; then
  APPS=("$ROOT"/desktop/dist/*.app)
  [ -d "${APPS[0]}" ] || fail "no app in desktop/dist (build one with desktop/build-mac.sh, or give --app)"
  [ "${#APPS[@]}" = 1 ] || fail "desktop/dist holds more than one app: give --app"
  APP="${APPS[0]}"
fi
# The executable its bundle names: BitcoinTX, or BitcoinTX Preview's own (#670);
# BitcoinTX when the bundle doesn't say
EXE=""
if [ -x /usr/libexec/PlistBuddy ] && [ -f "$APP/Contents/Info.plist" ]; then
  EXE="$(/usr/libexec/PlistBuddy -c "Print :CFBundleExecutable" "$APP/Contents/Info.plist" 2>/dev/null)" || EXE=""
fi
case "$EXE" in
  "") EXE=BitcoinTX ;;
  */*|.|..) fail "refusing $APP: its bundle names the executable $EXE" ;;
esac
BIN="$APP/Contents/MacOS/$EXE"
[ -x "$BIN" ] || fail "no app at $APP (build one with desktop/build-mac.sh, or give --app)"
if [ "$fresh" = 1 ]; then
  if answers; then
    fail "a BitcoinTX still answers on port $PORT: quit it before --fresh"
  fi
  if copy_runs; then
    fail "a test copy in $COPIES is still running but doesn't answer on port $PORT: wait for it to open, or quit it"
  fi
  for name in "${APP_FILES[@]}"; do rm -rf "${DATA:?}/$name"; done
fi

# WebKit keeps an app's cookies by bundle id, and a cookie ignores the port: a
# build run under the installed app's id (org.bitcointx.desktop, or BitcoinTX
# Preview's) shares its sign-in, so a test login logged the installed app out
# (#924). So the build runs as a copy with an id of its own, re-signed ad hoc,
# since the signature seals the id. A bundle with no Info.plist names no id.
if [ -f "$APP/Contents/Info.plist" ]; then
  SOURCE="$(physical "$APP")"
  in_folder "$SOURCE" "$COPIES" && fail "refusing $APP: it is this script's own copy (give the build it was made from)"
  COPY="$COPIES/$(basename "$SOURCE")"
  if answers; then
    # The test run that answers is this build's copy (a second launch, MAC-5):
    # it is in use, so it stays as it is
    [ "$(cat "$COPIES/.source" 2>/dev/null)" = "$SOURCE" ] && [ -x "$COPY/Contents/MacOS/$EXE" ] \
      || fail "a BitcoinTX that isn't this build's test copy answers on port $PORT: quit it first"
  elif copy_runs; then
    fail "a test copy in $COPIES is still running but doesn't answer on port $PORT: wait for it to open, or quit it"
  else
    make_copy
  fi
  BIN="$COPY/Contents/MacOS/$EXE"
fi

# A build older than BTCTX_DESKTOP_DATA_DIR (every release up to 1.2.5, the
# installed app) ignores it and uses ~/Library/Application Support: under
# this test home, that is inside the test folder too.
mkdir -p "$DATA/home"
export BTCTX_DESKTOP_DATA_DIR="$DATA" BTCTX_DESKTOP_PORT="$PORT" HOME="$DATA/home"
echo "BitcoinTX test run: data $DATA, http://127.0.0.1:$PORT${COPY:+, bundle id $(bundle_id "$COPY")}"
if [ "$background" = 1 ]; then
  mkdir -p "$DATA/logs"
  nohup "$BIN" >>"$DATA/logs/run-test-build.out" 2>&1 &
  echo "started, pid $!"
else
  exec "$BIN"
fi
