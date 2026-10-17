#!/usr/bin/env bash
# An update from the published 1.2.8 image, which ran BitcoinTX as root, to
# an image built here, which runs it as its own user, btctx (#202). CI's
# "Docker image + container smoke" job runs it; so can you, with Docker and
# the network (it pulls 1.2.8):
#
#   docker build -t btctx:ci . && scripts/docker_update_check.sh btctx:ci
#
# 1.2.8 makes a volume as users have one, every file root's: a ledger (the
# v0.7.0 test database, which it upgrades, so with a copy in backups/), its
# setup code and session key. The new image must take it over: the app runs
# as btctx, every file in /data is btctx's, the ledger and the setup code
# still work, the app and the CLI write. Then a restart where an ordinary
# user may not open port 80 (as in StartOS, or Docker's --network host), with
# only the capabilities a hardened setup keeps; and a 1.2.8 install whose
# DATABASE_FILE is on a volume of its own; and odd DATABASE_FILE paths that
# name / or the kernel's folders, never handed over (#446's reviews).
set -euo pipefail
cd "$(dirname "$0")/.."

NEW=${1:-btctx:ci}
# The published 1.2.8, by digest: version tags are never overwritten
OLD=ghcr.io/digimonk73/btctx-mcp:v1.2.8@sha256:85413741dada1a73ea78b50faeb99ea9374a0bf2a4ffbdeeaf4edf70e7254607
VOL=btctx-update-check
VOL2=btctx-update-check-elsewhere
PORT=${PORT:-8082}
PY=${PY:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}
URL=http://127.0.0.1:$PORT

cleanup() {
  docker rm -fv btctx-128 btctx-new >/dev/null 2>&1 || true
  docker volume rm "$VOL" "$VOL2" >/dev/null 2>&1 || true
}
failed() { docker logs btctx-new 2>&1 | tail -40 || true; }
trap cleanup EXIT
trap failed ERR
cleanup

start() {  # start <name> <image> [docker run options]: wait until it answers
  local name=$1 image=$2; shift 2
  docker run -d --name "$name" -p "127.0.0.1:$PORT:80" "$@" "$image" >/dev/null
  for _ in $(seq 1 60); do
    curl -sf -o /dev/null "$URL/" && return 0
    sleep 2
  done
  docker logs "$name"; return 1
}
all_btctx() {  # every file and folder in /data is btctx's
  local others
  others=$(docker exec -u btctx "$1" find "${2:-/data}" \( \! -user btctx -o \! -group btctx \) -print)
  [ -z "$others" ] || { echo "✗ not btctx's:"; echo "$others"; return 1; }
}
app_is_btctx() {  # the app (PID 1) runs as btctx: real, effective, saved, filesystem uid
  docker exec "$1" grep -qE '^Uid:\s+10001\s+10001\s+10001\s+10001$' /proc/1/status \
    || { echo "✗ the app isn't btctx:"; docker exec "$1" grep -E '^(Uid|Gid):' /proc/1/status; return 1; }
}

echo "1.2.8 (root) makes the volume"
docker volume create "$VOL" >/dev/null
docker run --rm -v "$VOL:/data" -v "$PWD/backend/tests/fixtures:/fx:ro" "$OLD" cp /fx/v0_7_0.db /data/btctx.db
start btctx-128 "$OLD" -v "$VOL:/data"
docker exec btctx-128 sh -c 'test -s /data/setup-code.txt -a -s /data/.btctx_secret_key && ls /data/backups/*.db >/dev/null'
docker exec btctx-128 sh -c 'test "$(stat -c %u /data/btctx.db)" = 0'   # the case to take over
CODE=$(docker exec btctx-128 cat /data/setup-code.txt)
docker rm -f btctx-128 >/dev/null

echo "$NEW takes it over"
start btctx-new "$NEW" -v "$VOL:/data"
app_is_btctx btctx-new
all_btctx btctx-new
"$PY" scripts/check_upgraded_instance.py --url "$URL" --setup-code "$CODE" --write
all_btctx btctx-new

echo "a restart where an ordinary user may not open port 80, with a hardened setup's capabilities"
docker rm -f btctx-new >/dev/null
start btctx-new "$NEW" -v "$VOL:/data" --sysctl net.ipv4.ip_unprivileged_port_start=1024 \
  --cap-drop ALL --cap-add CHOWN --cap-add SETUID --cap-add SETGID --cap-add NET_BIND_SERVICE
app_is_btctx btctx-new
"$PY" scripts/check_upgraded_instance.py --url "$URL" --setup-code "$CODE"

echo "the CLI as btctx (docker exec -u btctx) writes"
echo "update-check-456" | docker exec -i -u btctx btctx-new python -m backend.cli set-password --password-stdin >/dev/null
curl -sf -o /dev/null -X POST "$URL/api/login" -H 'content-type: application/json' \
  -d '{"username":"admin","password":"update-check-456"}'
docker exec -u btctx btctx-new python -m backend.cli recalculate >/dev/null
all_btctx btctx-new
docker rm -f btctx-new >/dev/null

echo "a 1.2.8 install whose DATABASE_FILE is on a volume of its own"
ELSEWHERE=(-e DATABASE_FILE=/srv/btctx/btctx.db -v "$VOL2:/srv/btctx")
start btctx-128 "$OLD" "${ELSEWHERE[@]}"
docker rm -f btctx-128 >/dev/null
start btctx-new "$NEW" "${ELSEWHERE[@]}"
app_is_btctx btctx-new
all_btctx btctx-new /srv/btctx
docker rm -f btctx-new >/dev/null

echo "odd DATABASE_FILE paths never hand over a folder of the image"
docker run --rm -v "$VOL2:/srv/btctx" --entrypoint ln "$NEW" -s / /srv/btctx/x   # as btctx would
for db in /./btctx.db /data/../btctx.db /dev/btctx.db /srv/btctx/x/dev/btctx.db; do
  owners=$(docker run --rm -v "$VOL2:/srv/btctx" -e DATABASE_FILE="$db" "$NEW" stat -c %u:%g /etc/passwd /app /dev/null)
  [ "$(echo $owners)" = "0:0 0:0 0:0" ] || { echo "✗ DATABASE_FILE=$db handed over: $owners"; exit 1; }
done

echo "✓ an update from 1.2.8's root-owned /data works, and every file is btctx's"
