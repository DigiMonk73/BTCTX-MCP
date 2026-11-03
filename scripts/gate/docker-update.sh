#!/usr/bin/env bash
# The release gate's figures across an update, on Docker, in one command
# (#848; docs/AGENT-TESTS.md, UPG-1 and UPG-2's "every figure identical"):
# the previous release's image on a new volume, the golden ledger loaded, its
# figures recorded; then the candidate's image on that same volume, its
# figures recorded and compared, PASS or FAIL per figure.
#
#   scripts/gate/docker-update.sh OLD_IMAGE NEW_IMAGE [OUT_DIR]
#   scripts/gate/docker-update.sh ghcr.io/digimonk73/btctx-mcp:v2.0.0 btctx:ci
#
# Throwaway only: its own volume, container and login, removed at the end;
# port $PORT (9551) on 127.0.0.1. The owner's BitcoinTX (8765) and Preview
# (8767) are checked before and after and must answer the same: the run
# stops if either changes. The snaps and the log stay in OUT_DIR (a new temp
# folder by default). Needs Docker, and the network for an image not pulled.
set -euo pipefail
cd "$(dirname "$0")/../.."

[ $# -ge 2 ] || { sed -n '2,16p' "$0"; exit 2; }
OLD=$1 NEW=$2
OUT=${3:-$(mktemp -d "${TMPDIR:-/tmp}/btctx-gate.XXXXXX")}
PORT=${PORT:-9551}
RUN=btctx-gate-$$
PY=${PY:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}
export BTCTX_URL=http://127.0.0.1:$PORT BTCTX_USER=gate-tester
BTCTX_PASSWORD=gate-$(od -An -N12 -tx1 /dev/urandom | tr -d ' \n')
export BTCTX_PASSWORD
mkdir -p "$OUT"

say() { printf '%s %s\n' "$(date -u +%H:%M:%SZ)" "$*"; }
owners() {  # what the owner's two apps answer now: none, or their health
  local port
  for port in 8765 8767; do
    printf '%s=%s ' "$port" "$(curl -s --noproxy '*' -m 2 "http://127.0.0.1:$port/api/health" || echo none)"
  done
}
OWNERS=$(owners)
guard() {
  [ "$(owners)" = "$OWNERS" ] || { say "FAIL the owner's ports changed: $OWNERS -> $(owners)"; exit 1; }
}
cleanup() {
  docker rm -fv "$RUN" >/dev/null 2>&1 || true
  docker volume rm "$RUN" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if curl -s --noproxy '*' -m 2 -o /dev/null "$BTCTX_URL/api/health"; then
  say "FAIL port $PORT already answers: stop what runs there, or set PORT"; exit 1
fi
say "the owner's ports before: $OWNERS"
docker volume create "$RUN" >/dev/null

start() {  # start IMAGE: a container on the volume, waited for, saying so while it waits
  local began=$SECONDS report=30
  docker rm -f "$RUN" >/dev/null 2>&1 || true
  guard
  say "starting $1 (pulls it first if needed)"
  docker run -d --name "$RUN" -p "127.0.0.1:$PORT:80" -v "$RUN:/data" "$1" >/dev/null
  until curl -sf --noproxy '*' -m 2 "$BTCTX_URL/api/health" >/dev/null; do
    if [ $((SECONDS - began)) -ge 300 ]; then
      docker logs "$RUN" 2>&1 | tail -30; say "FAIL $1 didn't answer in 5 minutes"; exit 1
    fi
    if [ $((SECONDS - began)) -ge $report ]; then
      say "still waiting for $1 ($((SECONDS - began)) s; it usually takes under 30)"; report=$((report + 30))
    fi
    sleep 1
  done
  say "$1 answers: $(curl -s --noproxy '*' "$BTCTX_URL/api/health")"
}

start "$OLD"
CODE=$(docker exec "$RUN" cat /data/setup-code.txt)
curl -sf --noproxy '*' -o /dev/null -X POST "$BTCTX_URL/api/users/reset-account" -H 'content-type: application/json' \
  -d "{\"username\":\"$BTCTX_USER\",\"password\":\"$BTCTX_PASSWORD\",\"setup_code\":\"$CODE\"}" \
  || { say "FAIL the throwaway login wasn't claimed"; exit 1; }
"$PY" scripts/gate/golden_loader.py
"$PY" scripts/gate/figures.py snap "$OUT/before.json"

start "$NEW"
"$PY" scripts/gate/figures.py snap "$OUT/after.json"
docker logs "$RUN" > "$OUT/new.log" 2>&1
guard
say "the owner's ports after: $(owners)"

set +e
"$PY" scripts/gate/figures.py compare "$OUT/before.json" "$OUT/after.json" | tee "$OUT/compare.txt"
verdict=${PIPESTATUS[0]}
say "snaps, the candidate's log and the comparison: $OUT"
exit "$verdict"
