#!/usr/bin/env bash
# Mirror startos/ to DigiMonk73/BTCTX-StartOS, the repository Start9's
# community registry forks: the mirror's root becomes exactly the committed
# contents of startos/, in one commit pointing at the source commit. The
# mirror's own Tag and Release workflow (Start9's) then tags it
# v<upstream>_<revision> and releases it; scripts/mirror-startos-release.sh
# does that by hand if it can't.
#
#   scripts/sync-startos-mirror.sh [--push] [MIRROR_DIR]
#
# MIRROR_DIR  an existing clone of the mirror, or where to clone it
#             (default: a new temporary directory)
# --push      push the commit; without it, it stays local to inspect
# MIRROR_URL  clone URL override (the release workflow passes one with a token)
# START9_FORK, START9_BRANCH, FORK_URL  Start9's fork, as for start9-pull.sh
#             (found with gh otherwise, so a sync by hand needs gh signed in)
#
# Only committed files are mirrored; uncommitted changes in startos/ abort.
# Once Start9 has forked the mirror, the commit goes on top of their fork's
# branch (below). Run scripts/start9-pull.sh first once Start9 has changed
# its fork, so this never undoes their changes.
set -euo pipefail

PUSH=false
if [ "${1:-}" = "--push" ]; then PUSH=true; shift; fi
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
URL="${MIRROR_URL:-https://github.com/DigiMonk73/BTCTX-StartOS.git}"
BRANCH="${MIRROR_BRANCH:-main}"
DIR="${1:-$(mktemp -d)/BTCTX-StartOS}"

if [ -n "$(git -C "$ROOT" status --porcelain -- startos)" ]; then
  echo "startos/ has uncommitted changes; commit them first" >&2
  exit 1
fi
SRC_SHA="$(git -C "$ROOT" rev-parse HEAD)"
VERSION="$(sed -n "s/.*version: '\([0-9.]*:[0-9]*\)'.*/\1/p" "$ROOT/startos/startos/versions/current.ts" | head -1)"
[ -n "$VERSION" ] || { echo "can't read the package version from current.ts" >&2; exit 1; }

if [ -d "$DIR/.git" ]; then
  git -C "$DIR" fetch -q origin "$BRANCH"
  git -C "$DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$URL" "$DIR"
fi

# Start our commit on top of Start9's fork, so a pull request from the mirror
# to it shows only our changes, not theirs undone. Normally their branch has
# merged ours and moved on: fast-forward. Already in ours (a pull request of
# ours still open there): nothing to do. Diverged (e.g. they squash-merged):
# record theirs as merged, keeping our tree. Either way our tree replaces
# theirs, so startos/ must already hold their changes: --check first, also
# for a docs-only sync by hand.
FORK_INFO="$("$ROOT/scripts/start9-pull.sh" --fork)"
read -r FORK FORK_BRANCH <<< "$FORK_INFO" || true
if [ -n "${FORK:-}" ]; then
  START9_FORK="$FORK" START9_BRANCH="$FORK_BRANCH" "$ROOT/scripts/start9-pull.sh" --check
  git -C "$DIR" fetch -q "${FORK_URL:-https://github.com/$FORK.git}" "$FORK_BRANCH" \
    || { echo "can't fetch $FORK ($FORK_BRANCH)" >&2; exit 1; }
  if git -C "$DIR" merge-base --is-ancestor FETCH_HEAD HEAD; then
    echo "$FORK $FORK_BRANCH is already in the mirror's $BRANCH."
  elif git -C "$DIR" merge-base --is-ancestor HEAD FETCH_HEAD; then
    git -C "$DIR" merge -q --ff-only FETCH_HEAD
    echo "Fast-forwarded the mirror's $BRANCH to $FORK $FORK_BRANCH ($(git -C "$DIR" rev-parse --short HEAD))."
  else
    git -C "$DIR" merge -q -s ours --allow-unrelated-histories --no-edit -m "Merge $FORK $FORK_BRANCH" FETCH_HEAD
    echo "WARNING: the mirror's $BRANCH and $FORK $FORK_BRANCH had diverged: merged it, keeping startos/ as the content." >&2
  fi
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
if $PUSH; then
  git -C "$DIR" push origin "HEAD:$BRANCH"
  echo "Pushed $BRANCH. The mirror's Tag and Release workflow tags and releases $VERSION."
else
  echo "Not pushed. Inspect $DIR, then: git -C $DIR push origin HEAD:$BRANCH"
fi
