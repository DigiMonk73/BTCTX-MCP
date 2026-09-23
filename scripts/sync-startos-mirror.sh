#!/usr/bin/env bash
# Mirror startos/ to DigiMonk73/BTCTX-StartOS, the repository Start9's
# community registry would fork: the mirror's root becomes exactly the
# committed contents of startos/, in one commit pointing at the source commit,
# tagged v<upstream>_<revision> (Start9's tag convention).
#
#   scripts/sync-startos-mirror.sh [--push] [MIRROR_DIR]
#
# MIRROR_DIR  an existing clone of the mirror, or where to clone it
#             (default: a new temporary directory)
# --push      push the commit and tag; without it they stay local to inspect
# MIRROR_URL  clone URL override (the release workflow passes one with a token)
#
# Only committed files are mirrored; uncommitted changes in startos/ abort.
set -euo pipefail

PUSH=false
if [ "${1:-}" = "--push" ]; then PUSH=true; shift; fi
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
URL="${MIRROR_URL:-https://github.com/DigiMonk73/BTCTX-StartOS.git}"
BRANCH="${MIRROR_BRANCH:-master}"
DIR="${1:-$(mktemp -d)/BTCTX-StartOS}"

if [ -n "$(git -C "$ROOT" status --porcelain -- startos)" ]; then
  echo "startos/ has uncommitted changes; commit them first" >&2
  exit 1
fi
SRC_SHA="$(git -C "$ROOT" rev-parse HEAD)"
VERSION="$(sed -n "s/.*version: '\([0-9.]*:[0-9]*\)'.*/\1/p" "$ROOT/startos/startos/versions/current.ts" | head -1)"
[ -n "$VERSION" ] || { echo "can't read the package version from current.ts" >&2; exit 1; }
TAG="v${VERSION/:/_}"

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH"
  git -C "$DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$URL" "$DIR"
fi

# Replace everything but .git with the committed startos/ tree.
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
git -C "$ROOT" archive HEAD startos | tar -x -C "$STAGE"
find "$DIR" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -a "$STAGE/startos/." "$DIR/"

git -C "$DIR" add -A
if git -C "$DIR" diff --cached --quiet; then
  echo "Mirror already matches startos/ at ${SRC_SHA:0:7}."
else
  git -C "$DIR" commit -q -m "Sync from DigiMonk73/BTCTX-MCP@${SRC_SHA:0:7} ($VERSION)" \
    -m "Source: https://github.com/DigiMonk73/BTCTX-MCP/tree/$SRC_SHA/startos"
  echo "Committed $(git -C "$DIR" rev-parse --short HEAD) in $DIR"
fi
if ! git -C "$DIR" rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  git -C "$DIR" tag "$TAG"
fi

if $PUSH; then
  git -C "$DIR" push origin "HEAD:$BRANCH"
  if git -C "$DIR" push origin "refs/tags/$TAG"; then
    echo "Pushed $BRANCH and $TAG."
  else
    echo "Pushed $BRANCH; warning: couldn't push tag $TAG (push it by hand)." >&2
  fi
else
  echo "Not pushed. Inspect $DIR, then: git -C $DIR push origin HEAD:$BRANCH $TAG"
fi
