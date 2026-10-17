#!/usr/bin/env bash
# Build the Docker image from the checked-out code and run CI's container
# checks against it on this machine: `make docker-smoke`.
#
# A throwaway container on 127.0.0.1:${PORT:-8778} with its own empty /data
# volume, removed at the end (pass --keep to leave it running). Same checks
# as the "Docker image + container smoke" job in .github/workflows/ci.yml:
# claim with the setup code, the smoke test (live prices, so price steps may
# be skipped until a price source is chosen), data on /data, the app as its
# own user (btctx), health, CLI. The update from 1.2.8 is its own script,
# scripts/docker_update_check.sh.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT=${PORT:-8778}
NAME=btctx-local-smoke
IMAGE=btctx:local
PY=${PY:-$( [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3 )}
KEEP=${1:-}

cleanup() {
  [ "$KEEP" = "--keep" ] || docker rm -fv "$NAME" >/dev/null 2>&1 || true
  [ -z "${TMP_CONFIG:-}" ] || rm -rf "$TMP_CONFIG"   # a failed test here would fail the script
}
trap cleanup EXIT

# The base images are public: a blank Docker config skips the credential
# helper (docker-credential-desktop), which hangs where there's no keychain,
# e.g. in an AI agent's sandboxed shell. Same engine, same build plugins.
if [ -z "${DOCKER_CONFIG:-}" ]; then
  DOCKER_HOST=${DOCKER_HOST:-$(docker context inspect --format '{{.Endpoints.docker.Host}}')}
  TMP_CONFIG=$(mktemp -d)
  echo '{}' > "$TMP_CONFIG/config.json"
  [ -d "$HOME/.docker/cli-plugins" ] && ln -s "$HOME/.docker/cli-plugins" "$TMP_CONFIG/cli-plugins"
  export DOCKER_HOST DOCKER_CONFIG=$TMP_CONFIG
fi

docker build -t "$IMAGE" .
docker rm -fv "$NAME" >/dev/null 2>&1 || true
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:80" "$IMAGE" >/dev/null
for i in $(seq 1 60); do
  curl -sf -o /dev/null "http://127.0.0.1:$PORT/" && break
  [ "$i" = 60 ] && { docker logs "$NAME"; exit 1; }
  sleep 2
done

docker logs "$NAME" 2>&1 | grep -q "First-run setup code: "
CODE=$(docker exec "$NAME" cat /data/setup-code.txt)
"$PY" scripts/smoke_test.py --url "http://127.0.0.1:$PORT" \
  --user local-owner --password local-password-123 --setup-code "$CODE"
docker exec "$NAME" sh -c '! test -e /data/setup-code.txt'
docker exec "$NAME" test -s /data/btctx.db -a -s /data/.btctx_secret_key
# The app runs as its own user, btctx, never root, and /data is all its (#202)
docker exec "$NAME" grep -qE '^Uid:\s+10001\s+10001\s+10001\s+10001$' /proc/1/status
test -z "$(docker exec "$NAME" find /data \( \! -user btctx -o \! -group btctx \) -print)"

curl -sf "http://127.0.0.1:$PORT/api/health" | grep -q "\"version\":\"$(tr -d '[:space:]' < VERSION)\""
docker exec -u btctx "$NAME" python -m backend.cli migrate | grep -q "up to date"
echo "local-password-456" | docker exec -i -u btctx "$NAME" python -m backend.cli set-password --password-stdin >/dev/null
curl -sf -o /dev/null -X POST "http://127.0.0.1:$PORT/api/login" -H 'content-type: application/json' \
  -d '{"username":"local-owner","password":"local-password-456"}'
docker exec -u btctx "$NAME" python -m backend.cli recalculate >/dev/null

echo "✓ Docker image from this checkout passed the container checks"
[ "$KEEP" = "--keep" ] && echo "  still running: http://127.0.0.1:$PORT (docker rm -fv $NAME to remove)"
exit 0
