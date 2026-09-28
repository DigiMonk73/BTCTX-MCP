#!/usr/bin/env bash
# Bring Start9's changes to their fork of the StartOS package (template
# updates, SDK bumps, review fixes) into startos/ here, so the next mirror
# sync (sync-startos-mirror.sh) never undoes them. Once Start9 has forked the
# mirror, run this on develop before every sync.
#
#   scripts/start9-pull.sh [--apply]
#
# Without --apply: shows what Start9 changed (their fork's main since it last
# took ours from the mirror). With --apply: applies it to startos/ in the
# working tree, three-way, for you to review, test and commit on develop.
#
# START9_FORK    their fork (default Start9-Community/BTCTX-StartOS)
# START9_BRANCH  its branch (default main)
# MIRROR_REPO    our mirror (default DigiMonk73/BTCTX-StartOS)
# FORK_URL, MIRROR_URL  clone URL overrides (e.g. local copies to try it)
set -euo pipefail

APPLY=false
if [ "${1:-}" = "--apply" ]; then APPLY=true; shift; fi
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
FORK="${START9_FORK:-Start9-Community/BTCTX-StartOS}"
FORK_BRANCH="${START9_BRANCH:-main}"
MIRROR="${MIRROR_REPO:-DigiMonk73/BTCTX-StartOS}"
FORK_URL="${FORK_URL:-https://github.com/$FORK.git}"
MIRROR_URL="${MIRROR_URL:-https://github.com/$MIRROR.git}"

if $APPLY; then
  BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
  [ "$BRANCH" = develop ] || { echo "on $BRANCH: switch to develop first" >&2; exit 1; }
  if [ -n "$(git -C "$ROOT" status --porcelain -- startos)" ]; then
    echo "startos/ has uncommitted changes; commit them first" >&2
    exit 1
  fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone -q --branch main "$MIRROR_URL" "$TMP/mirror"
git -C "$TMP/mirror" fetch -q "$FORK_URL" "$FORK_BRANCH:start9" \
  || { echo "can't fetch $FORK ($FORK_BRANCH): has Start9 forked it yet?" >&2; exit 1; }

# Their changes only: since the last commit both share (three dots).
git -C "$TMP/mirror" diff --binary main...start9 > "$TMP/start9.patch"
if [ ! -s "$TMP/start9.patch" ]; then
  echo "Nothing new from $FORK since it last took the mirror."
  exit 0
fi
git -C "$TMP/mirror" log --oneline main..start9
git -C "$TMP/mirror" diff --stat main...start9

if ! $APPLY; then
  echo
  echo "Full diff: git -C <clone of $MIRROR> diff main...start9 (after fetching $FORK). Apply with --apply."
  exit 0
fi
if git -C "$ROOT" apply --3way --directory=startos "$TMP/start9.patch"; then
  echo "Applied to startos/. Review (git diff), run the StartOS checks, then commit on develop."
else
  echo "Some hunks didn't apply cleanly: resolve the conflict markers in startos/, then commit." >&2
  exit 1
fi
