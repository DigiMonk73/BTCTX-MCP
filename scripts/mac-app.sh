#!/usr/bin/env bash
# The Mac app's checks and files in CI (ci.yml's macos-app job, release.yml's
# macos job: the same steps in both), with the app's name, executable, port
# and file names taken from the build in desktop/dist, never written in: a
# release builds BitcoinTX.app, a 2.0 pre-release "BitcoinTX Beta.app"
# (2.0 plan 7.4, B10a), each with its own folders and port.
#
#   scripts/mac-app.sh check                        launch it, check its API
#   scripts/mac-app.sh package >> "$GITHUB_OUTPUT"  <Name>-macOS.dmg and .zip (stem=, dmg=, zip=)
#   scripts/mac-app.sh identity NAME BUNDLE_ID PORT may VERSION's build be that?
#
# check and package run only on GitHub's own runners: they open the build as
# it is, on its own data folder, and a 1.x build's is the installed app's, the
# real ledger. Anywhere else (a self-hosted runner too) a build runs only
# through desktop/run-test-build.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME=BitcoinTX APP_ID=org.bitcointx.desktop APP_PORT=8765 TEST_PORT=8766

fail() { echo "mac-app.sh: $*" >&2; exit 1; }
lower() { printf '%s' "$1" | tr '[:upper:]' '[:lower:]'; }

# A release build is the installed app; a beta build never is, in any case
# or on any port it could share (macOS folders and bundle ids ignore case)
identity() {
  local name="$1" id="$2" port="$3" version
  version="$(tr -d '[:space:]' < "$ROOT/VERSION")"
  if [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    [ "$name" = "$APP_NAME" ] && [ "$id" = "$APP_ID" ] && [ "$port" = "$APP_PORT" ] \
      || fail "a release build is $APP_NAME ($APP_ID) on port $APP_PORT, not $name ($id) on port $port"
  elif [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+-beta\.[1-9][0-9]*$ ]]; then
    [ "$(lower "$name")" != "$(lower "$APP_NAME")" ] || fail "the beta $version is called $name: the installed app's name"
    [ "$(lower "$id")" != "$(lower "$APP_ID")" ] || fail "the beta $version is $id: the installed app's bundle id"
    [ "$port" != "$APP_PORT" ] || fail "the beta $version answers on $port: the installed app's port"
    [ "$port" != "$TEST_PORT" ] || fail "the beta $version answers on $port: desktop/run-test-build.sh's port"
  else
    fail "bad VERSION: $version"
  fi
}

on_ci() {
  [ "${GITHUB_ACTIONS:-}" = true ] && [ "${RUNNER_ENVIRONMENT:-}" = github-hosted ] \
    || fail "only on GitHub's runners: it opens the build's own data folder (a 1.x build's is the real ledger). Run a build with desktop/run-test-build.sh"
}

# The one app build-mac.sh made
the_app() {
  local apps=("$ROOT"/desktop/dist/*.app)
  [ "${#apps[@]}" = 1 ] && [ -d "${apps[0]}" ] || fail "desktop/dist holds no single .app: ${apps[*]}"
  APP="${apps[0]}"
  NAME="$(basename "$APP" .app)"
  plist() { /usr/libexec/PlistBuddy -c "Print :$1" "$APP/Contents/Info.plist"; }
  EXE="$APP/Contents/MacOS/$(plist CFBundleExecutable)"
  ID="$(plist CFBundleIdentifier)"
  [ -x "$EXE" ] || fail "$EXE is not executable"
}

# The port the launched app listens on, once it does; nothing before (lsof
# then fails, which pipefail would make this script's end)
listening_port() {
  { lsof -nP -a -p "$1" -iTCP -sTCP:LISTEN -Fn 2>/dev/null || true; } | sed -n 's/^n.*:\([0-9][0-9]*\)$/\1/p' | head -1
}

stop() {
  kill "$1" 2>/dev/null || return 0
  for _ in $(seq 1 10); do kill -0 "$1" 2>/dev/null || return 0; sleep 1; done
  kill -9 "$1" 2>/dev/null || true
}

check() {
  on_ci
  the_app
  "$EXE" > app.log 2>&1 &
  local pid=$! port="" code
  trap 'stop '"$pid" EXIT
  for _ in $(seq 1 60); do
    port="$(listening_port "$pid")"
    if [ -n "$port" ] && curl -sf -o /dev/null "http://127.0.0.1:$port/"; then break; fi
    kill -0 "$pid" 2>/dev/null || { cat app.log; fail "$NAME quit before it answered"; }
    port=""
    sleep 2
  done
  [ -n "$port" ] || { cat app.log; fail "$NAME never answered"; }
  echo "$NAME ($ID) answers on port $port"
  local health
  health="$(curl -sf "http://127.0.0.1:$port/api/health" || true)"
  [[ "$health" == *'"status":"ok"'* ]] || fail "/api/health isn't ok: $health"
  code="$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://127.0.0.1:$port/api/import/entries/preview" \
    -H 'content-type: application/json' -d '{"rows":[]}' || true)"
  echo "entries endpoint (anonymous) -> $code"
  [ "$code" = 401 ] || fail "an anonymous import preview answered $code, not 401"
  identity "$NAME" "$ID" "$port"
  # Its data in its own folder; a beta's never in the installed app's
  [ -d "$HOME/Library/Application Support/$NAME" ] || fail "no data folder ~/Library/Application Support/$NAME"
  if [ "$NAME" != "$APP_NAME" ]; then
    for folder in "Application Support/$APP_NAME" "Logs/$APP_NAME"; do
      [ ! -e "$HOME/Library/$folder" ] || fail "$NAME made ~/Library/$folder, the installed app's"
    done
  fi
}

package() {
  on_ci
  the_app
  local stem="${NAME// /-}-macOS"
  ditto -c -k --keepParent "$APP" "$stem.zip"
  rm -rf dmg && mkdir dmg
  cp -R "$APP" dmg/
  ln -s /Applications dmg/Applications
  hdiutil create -volname "$NAME" -srcfolder dmg -ov -format UDZO "$stem.dmg" >&2
  hdiutil verify "$stem.dmg" >&2
  printf '%s\n' "stem=$stem" "dmg=$stem.dmg" "zip=$stem.zip"
}

case "${1:-}" in
  check) check ;;
  package) package ;;
  identity) [ $# = 4 ] || fail "usage: scripts/mac-app.sh identity NAME BUNDLE_ID PORT"; identity "$2" "$3" "$4" ;;
  *) fail "usage: scripts/mac-app.sh check | package | identity NAME BUNDLE_ID PORT" ;;
esac
