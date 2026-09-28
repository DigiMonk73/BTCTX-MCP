#!/usr/bin/env bash
# Bring Start9's changes to their fork of the StartOS package (template
# updates, SDK bumps, review fixes) into startos/ here, so the next mirror
# sync (sync-startos-mirror.sh) never undoes them. Once Start9 has forked the
# mirror, run this on develop before every sync.
#
#   scripts/start9-pull.sh [--apply]
#
# Without --apply: shows how their fork's main differs from our mirror's main.
# Once they have merged our latest mirror commit (merge or squash), that is
# exactly their changes; while a pull request of ours is still open there, it
# also holds the reverse of ours, and the script says so. Changes already
# brought back and synced to the mirror no longer show. With --apply: applies
# the difference to startos/ in the working tree, three-way, for you to
# review, test and commit on develop.
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

# The fork's tree against the mirror's (two dots: trees, not history, so a
# squash-merged pull request of ours doesn't count as theirs).
git -C "$TMP/mirror" diff --binary main start9 > "$TMP/start9.patch"
if [ ! -s "$TMP/start9.patch" ]; then
  echo "$FORK matches the mirror: nothing to take."
  exit 0
fi
OPEN="$(gh pr list -R "$FORK" --state open --json headRepositoryOwner,number,title \
  --jq '.[] | select(.headRepositoryOwner.login == "'"${MIRROR%%/*}"'") | "#\(.number) \(.title)"' 2>/dev/null || true)"
if [ -n "$OPEN" ]; then
  echo "WARNING: our pull request(s) on $FORK are still open:" >&2
  echo "$OPEN" >&2
  echo "The difference below also undoes what they contain; take only Start9's own hunks." >&2
fi
git -C "$TMP/mirror" log --oneline main..start9
git -C "$TMP/mirror" diff --stat main start9

if ! $APPLY; then
  echo
  echo "Full diff: git -C <clone of $MIRROR> diff main start9 (after fetching $FORK). Apply with --apply."
  exit 0
fi
if git -C "$ROOT" apply --3way --directory=startos "$TMP/start9.patch"; then
  git -C "$ROOT" reset -q -- startos  # unstaged, so plain git diff shows it
  echo "Applied to startos/. Review (git diff), run the StartOS checks, then commit on develop."
else
  echo "Some hunks didn't apply cleanly: resolve the conflict markers in startos/ (git status), then commit." >&2
  exit 1
fi
