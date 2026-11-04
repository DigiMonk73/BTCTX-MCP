#!/usr/bin/env bash
# Bring Start9's changes to their fork of the StartOS package (template
# updates, SDK bumps, review fixes) into startos/ here, so the next mirror
# sync (sync-startos-mirror.sh) never undoes them. Once Start9 has forked the
# mirror, run this before every sync, on a branch cut from develop (develop
# takes changes only by pull request); the release workflow runs --check and
# stops if you haven't.
#
#   scripts/start9-pull.sh [--apply | --check | --fork]
#
# No option: shows what Start9 changed on their fork's default branch: since
# the commit of theirs we last took (scripts/start9-taken, until a sync is
# built on it), or else against our mirror's main. Once they have merged our
# latest mirror commit (merge or squash), that is exactly their changes;
# while a pull request of ours is still open there, the mirror comparison
# also holds the reverse of ours, and the script says so.
# --apply: applies that difference to startos/ in the working tree,
# three-way, for you to review, test, commit and send to develop by pull
# request, and records their commit in scripts/start9-taken (commit it too:
# later runs then count only what they changed since). Refused on main.
# --check: exit 1 if their changes are not in startos/ (committed: at HEAD,
# or in the commit since our last sync that took them, edited since; nothing
# new since the recorded commit counts as taken, so the record is only as
# true as the commit that carries it);
# exit 0 when they are, when there is no fork yet, or when their branch is
# already in the mirror's history (what differs is ours, waiting for them).
# Start9 changes made while a pull request of ours is open there can't be
# told from ours: exit 1, so no sync records them as taken without them.
# --fork: prints "<owner/repo> <branch>" of their fork, nothing before it exists.
#
# START9_FORK    their fork (default: the mirror's fork owned by Start9-Community,
#                found through the GitHub API; set it if they made a new repo)
# START9_BRANCH  its branch (default: the fork's default branch)
# MIRROR_REPO    our mirror (default DigiMonk73/BTCTX-StartOS)
# FORK_URL, MIRROR_URL  clone URL overrides (e.g. local copies to try it)
set -euo pipefail

MODE="${1:-show}"
case "$MODE" in show | --apply | --check | --fork) ;; *) echo "usage: $0 [--apply | --check | --fork]" >&2; exit 2 ;; esac
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
MIRROR="${MIRROR_REPO:-DigiMonk73/BTCTX-StartOS}"

FORK="${START9_FORK:-}"
if [ -z "$FORK" ]; then
  FORKS="$(gh api "repos/$MIRROR/forks" --paginate \
    --jq '.[] | select(.owner.login == "Start9-Community") | .full_name')" \
    || { echo "can't list the forks of $MIRROR (gh api)" >&2; exit 1; }
  FORK="${FORKS%%$'\n'*}"
fi
if [ -z "$FORK" ]; then
  case "$MODE" in
    --fork) exit 0 ;;
    --check) echo "Start9 hasn't forked $MIRROR yet: nothing to take."; exit 0 ;;
    *) echo "Start9 hasn't forked $MIRROR yet (or set START9_FORK=Owner/Repo)." >&2; exit 1 ;;
  esac
fi
FORK_BRANCH="${START9_BRANCH:-$(gh api "repos/$FORK" --jq .default_branch)}"
if [ "$MODE" = --fork ]; then
  echo "$FORK $FORK_BRANCH"
  exit 0
fi
FORK_URL="${FORK_URL:-https://github.com/$FORK.git}"
MIRROR_URL="${MIRROR_URL:-https://github.com/$MIRROR.git}"

if [ "$MODE" = --apply ]; then
  BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"
  [ "$BRANCH" != main ] || { echo "on main: cut a branch from develop first (git switch -c start9-changes origin/develop)" >&2; exit 1; }
  if [ -n "$(git -C "$ROOT" status --porcelain -- startos)" ]; then
    echo "startos/ has uncommitted changes; commit them first" >&2
    exit 1
  fi
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git clone -q --branch main "$MIRROR_URL" "$TMP/mirror"
git -C "$TMP/mirror" fetch -q "$FORK_URL" "$FORK_BRANCH:start9" \
  || { echo "can't fetch $FORK ($FORK_BRANCH)" >&2; exit 1; }

# Their branch already in the mirror's history (the sync builds on it, and
# they haven't committed since): whatever differs is ours, not yet merged there.
if git -C "$TMP/mirror" merge-base --is-ancestor start9 main; then
  echo "$FORK $FORK_BRANCH is already in the mirror: nothing to take."
  exit 0
fi

# What to compare their branch with. scripts/start9-taken records the commit
# of theirs that --apply last took (committed with the take-back, so squash
# merges don't lose it): then only what they did since counts, and it is
# exactly theirs. Without a record, the mirror's main: two dots, trees not
# history, so a squash-merged pull request of ours doesn't count as theirs;
# while one of ours is open there, that also holds the reverse of ours.
TAKEN_FILE="$ROOT/scripts/start9-taken"
TAKEN="$( { git -C "$ROOT" show HEAD:scripts/start9-taken 2>/dev/null || true; } | sed -n 1p | tr -cd '0-9a-f')"  # committed: what a release builds
# The record counts only while no sync has been built on it yet (after that,
# the mirror's main is the right base again), and only if the commit that
# last set it also changed startos/ (the take-back came with it).
RECORDED_IN="$(git -C "$ROOT" log -1 --format=%H HEAD -- scripts/start9-taken 2>/dev/null || true)"
BASE=main
if [ -n "$TAKEN" ] \
  && git -C "$TMP/mirror" merge-base --is-ancestor "$TAKEN" start9 2>/dev/null \
  && ! git -C "$TMP/mirror" merge-base --is-ancestor "$TAKEN" main 2>/dev/null \
  && [ -n "$RECORDED_IN" ] \
  && [ -n "$(git -C "$ROOT" diff-tree --no-commit-id --name-only -r "$RECORDED_IN" -- startos)" ]; then
  BASE="$TAKEN"
fi
git -C "$TMP/mirror" diff --binary "$BASE" start9 > "$TMP/start9.patch"
if [ ! -s "$TMP/start9.patch" ]; then
  if [ "$BASE" = main ]; then echo "$FORK matches the mirror: nothing to take."
  else echo "$FORK has nothing new since ${TAKEN:0:7}, which startos/ took: nothing to take."; fi
  exit 0
fi
OPEN=""
if [ "$BASE" = main ]; then
  OPEN="$(gh pr list -R "$FORK" --state open --json headRepositoryOwner,number,title \
    --jq '.[] | select(.headRepositoryOwner.login == "'"${MIRROR%%/*}"'") | "#\(.number) \(.title)"' 2>/dev/null || true)"
fi

if [ "$MODE" = --check ]; then
  # Their changes are in startos/ when the patch un-applies there: at HEAD,
  # or at the commit since our last sync that took them (a later change of
  # ours to the same lines no longer un-applies it, and is fine: the pull
  # request to them shows it). Committed only: the release builds HEAD.
  SYNCED="$(git -C "$TMP/mirror" log --format=%s main start9 \
    | sed -n 's/^Sync from DigiMonk73\/BTCTX-MCP@\([0-9a-f]*\).*/\1/p' | sed -n 1p)"  # reads it all: no SIGPIPE under pipefail
  HEAD_SHA="$(git -C "$ROOT" rev-parse HEAD)"
  COMMITS="$HEAD_SHA"
  if [ -n "$SYNCED" ] && git -C "$ROOT" merge-base --is-ancestor "$SYNCED" HEAD 2>/dev/null; then
    COMMITS="$COMMITS $(git -C "$ROOT" rev-list HEAD "^$SYNCED" -- startos)"
  fi
  for C in $COMMITS; do
    GIT_INDEX_FILE="$TMP/index" git -C "$ROOT" read-tree "$C:startos"
    if GIT_INDEX_FILE="$TMP/index" git -C "$ROOT" apply --cached --check --reverse "$TMP/start9.patch" 2>/dev/null; then
      if [ "$C" = "$HEAD_SHA" ]; then
        echo "Start9's changes to $FORK are in startos/."
      else
        echo "Start9's changes to $FORK are in startos/: taken in $(git -C "$ROOT" log -1 --format='%h %s' "$C"), changed since."
      fi
      exit 0
    fi
  done
  git -C "$TMP/mirror" diff --stat "$BASE" start9 >&2
  if [ -n "$OPEN" ]; then
    echo "Start9 changed $FORK while our pull request there is still open ($OPEN), so their changes can't be told from ours. Ask them to merge (or close) it, then take their changes: scripts/start9-pull.sh --apply on a branch cut from develop." >&2
    exit 1
  fi
  echo "Start9 changed $FORK, and startos/ doesn't have it yet. On a branch cut from develop: scripts/start9-pull.sh --apply, review, run the checks, commit and open a pull request into develop; then release again (startos/UPDATING.md, \"After Start9 forks the mirror\")." >&2
  exit 1
fi

if [ -n "$OPEN" ]; then
  echo "WARNING: our pull request(s) on $FORK are still open:" >&2
  echo "$OPEN" >&2
  echo "The difference below also undoes what they contain; take only Start9's own hunks." >&2
fi
git -C "$TMP/mirror" log --oneline "$BASE..start9"
git -C "$TMP/mirror" diff --stat "$BASE" start9

if [ "$MODE" = show ]; then
  echo
  echo "Full diff: git -C <clone of $MIRROR> diff $BASE start9 (after fetching $FORK). Apply with --apply."
  exit 0
fi
if git -C "$ROOT" apply --3way --directory=startos "$TMP/start9.patch"; then
  git -C "$ROOT" reset -q -- startos  # unstaged, so plain git diff shows it
  git -C "$TMP/mirror" rev-parse start9 > "$TAKEN_FILE"
  echo "Applied to startos/, and scripts/start9-taken records what was taken. Review (git diff), run the StartOS checks, then commit both and open a pull request into develop."
else
  echo "Some hunks didn't apply cleanly: resolve the conflict markers in startos/ (git status), then commit." >&2
  exit 1
fi
