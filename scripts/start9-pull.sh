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
# No option: shows how their fork's default branch differs from our mirror's
# main. Once they have merged our latest mirror commit (merge or squash), that
# is exactly their changes; while a pull request of ours is still open there,
# it also holds the reverse of ours, and the script says so. Changes already
# brought back and synced to the mirror no longer show.
# --apply: applies that difference to startos/ in the working tree,
# three-way, for you to review, test, commit and send to develop by pull
# request. Refused on main.
# --check: exit 1 if their changes are not in startos/ (committed: at HEAD,
# or in the commit since our last sync that took them, edited since);
# exit 0 when they are, when there is no fork yet, or while a pull request of
# ours is open there (it can't tell theirs from ours then; it says so).
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

# The fork's tree against the mirror's (two dots: trees, not history, so a
# squash-merged pull request of ours doesn't count as theirs).
git -C "$TMP/mirror" diff --binary main start9 > "$TMP/start9.patch"
if [ ! -s "$TMP/start9.patch" ]; then
  echo "$FORK matches the mirror: nothing to take."
  exit 0
fi
OPEN="$(gh pr list -R "$FORK" --state open --json headRepositoryOwner,number,title \
  --jq '.[] | select(.headRepositoryOwner.login == "'"${MIRROR%%/*}"'") | "#\(.number) \(.title)"' 2>/dev/null || true)"

if [ "$MODE" = --check ]; then
  # Their changes are in startos/ when the patch un-applies there: at HEAD,
  # or at the commit since our last sync that took them (a later change of
  # ours to the same lines no longer un-applies it, and is fine: the pull
  # request to them shows it). Committed only: the release builds HEAD.
  SYNCED="$(git -C "$TMP/mirror" log -1 --format=%s --grep='^Sync from DigiMonk73/BTCTX-MCP@' main start9 \
    | sed -n 's/^Sync from DigiMonk73\/BTCTX-MCP@\([0-9a-f]*\).*/\1/p')"
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
  if [ -n "$OPEN" ]; then
    echo "::warning::Our pull request on $FORK is still open ($OPEN), so Start9's own changes can't be told apart: check with scripts/start9-pull.sh."
    exit 0
  fi
  git -C "$TMP/mirror" diff --stat main start9 >&2
  echo "Start9 changed $FORK, and startos/ doesn't have it yet. On a branch cut from develop: scripts/start9-pull.sh --apply, review, run the checks, commit and open a pull request into develop; then release again (startos/UPDATING.md, \"After Start9 forks the mirror\")." >&2
  exit 1
fi

if [ -n "$OPEN" ]; then
  echo "WARNING: our pull request(s) on $FORK are still open:" >&2
  echo "$OPEN" >&2
  echo "The difference below also undoes what they contain; take only Start9's own hunks." >&2
fi
git -C "$TMP/mirror" log --oneline main..start9
git -C "$TMP/mirror" diff --stat main start9

if [ "$MODE" = show ]; then
  echo
  echo "Full diff: git -C <clone of $MIRROR> diff main start9 (after fetching $FORK). Apply with --apply."
  exit 0
fi
if git -C "$ROOT" apply --3way --directory=startos "$TMP/start9.patch"; then
  git -C "$ROOT" reset -q -- startos  # unstaged, so plain git diff shows it
  echo "Applied to startos/. Review (git diff), run the StartOS checks, then commit and open a pull request into develop."
else
  echo "Some hunks didn't apply cleanly: resolve the conflict markers in startos/ (git status), then commit." >&2
  exit 1
fi
