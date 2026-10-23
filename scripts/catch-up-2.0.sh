#!/usr/bin/env bash
# Keep the 2.0 build up to date with develop (AGENTS.md, "Branches": develop
# comes into 2.0 before every 2.0 step; the build's lead runs this nightly
# too, so 1.x's fixes never wait for the next step).
#
#   scripts/catch-up-2.0.sh [--dry-run]      (make catch-up-2.0)
#
# Fetches from GitHub; when develop has commits 2.0 lacks:
# - stops for the build's lead ("needs the lead:", nothing opened) on what a
#   plain merge can't take: a 1.x migration (2.0's first migration is
#   re-pointed after it, docs/temp/2.0-accounts.md 7.2: the database, the
#   owner's "merge") or a conflict;
# - else opens "develop into 2.0, <date>" from develop itself, with auto-merge
#   as a merge commit (never a squash), or names the one already open;
# - and lists what the lead does next beside it ("to do:"): a new 1.x
#   release (B1's reference_1x.db is made again from it), changes to startos/
#   (2.0's package step, B9, builds on them).
# Ends with one line: UP TO DATE, CATCH-UP OPEN <url>, or NEEDS THE LEAD.
# Exit 0, but 1 when the lead must step in, 2 when it can't tell.
set -euo pipefail

DRY=false
case "${1:-}" in "") ;; --dry-run) DRY=true ;; *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;; esac
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
g() { git -C "$ROOT" "$@"; }
REPO="$(g remote get-url origin | sed -E 's#(\.git)?/*$##; s#.*[:/]([^/]+/[^/]+)$#\1#')"
OURS=origin/2.0 THEIRS=origin/develop
FIXTURE_SCRIPT=backend/tests/fixtures/make_reference_1x_db.py

g fetch -q origin develop 2.0 '+refs/tags/v*:refs/tags/v*' \
  || { echo "can't reach GitHub (git fetch failed): nothing checked" >&2; exit 2; }

behind="$(g rev-list --count "$OURS..$THEIRS")"
if [ "$behind" = 0 ]; then
  echo "UP TO DATE: 2.0 has everything on develop."
  exit 0
fi
echo "develop has $behind commit(s) 2.0 lacks:"
g log --oneline --no-merges "$OURS..$THEIRS" | sed 's/^/  /'

STOPS=() TODO=()
base="$(g merge-base "$OURS" "$THEIRS")"
migrations="$(g diff --name-only --diff-filter=A "$base" "$THEIRS" -- backend/migrations/versions/ | grep '\.py$' || true)"
[ -z "$migrations" ] || STOPS+=("a 1.x migration ($(echo "$migrations" | xargs -n1 basename | tr '\n' ' ' | sed 's/ $//')): merge it in a 2.0-merge-develop branch and re-point 2.0's first migration after it, for the owner's \"merge\" (7.2, point 2)")
g merge-tree --write-tree --quiet "$OURS" "$THEIRS" >/dev/null 2>&1 \
  || STOPS+=("the merge conflicts: merge develop in a 2.0-merge-develop branch and resolve it there")

released="$(g tag -l 'v1.*' --sort=-v:refname | grep -E '^v1\.[0-9]+\.[0-9]+$' | head -1 || true)"
fixture="$(g show "$OURS:$FIXTURE_SCRIPT" 2>/dev/null | sed -nE 's/^RELEASE = "(v[0-9.]+)"$/\1/p' || true)"
if [ -n "$released" ] && [ -n "$fixture" ] && [ "$released" != "$fixture" ] \
   && [ "$(printf '%s\n%s\n' "$released" "$fixture" | sort -V | tail -1)" = "$released" ]; then
  TODO+=("$released is out: make reference_1x.db again from it ($FIXTURE_SCRIPT --release $released), once this merge is in")
fi
startos="$(g diff --name-only "$base" "$THEIRS" -- startos/ | wc -l | tr -d ' ')"
[ "$startos" = 0 ] || TODO+=("$startos file(s) under startos/ changed (SDK, start-cli, the package): note them on #251 for 2.0's package step (B9)")

for item in "${TODO[@]+"${TODO[@]}"}"; do echo "to do: $item"; done
if [ ${#STOPS[@]} -gt 0 ]; then
  for item in "${STOPS[@]}"; do echo "needs the lead: $item"; done
  echo "NEEDS THE LEAD: nothing opened."
  exit 1
fi

# One already open: from develop, or from a 2.0-merge-develop branch the lead made
open="$(gh pr list -R "$REPO" --base 2.0 --state open --json url,headRefName \
  --jq '[.[] | select(.headRefName == "develop" or (.headRefName | startswith("2.0-merge-develop")))][0].url // empty')" \
  || { echo "gh can't list the pull requests: nothing opened" >&2; exit 2; }
if [ -z "$open" ] && ! $DRY; then
  open="$(gh pr create -R "$REPO" --base 2.0 --head develop --title "develop into 2.0, $(date +%Y-%m-%d)" \
    --body "1.x's latest work into the 2.0 build (\`docs/temp/2.0-accounts.md\` 7.2, point 2), merged with a merge commit, never a squash: each change was reviewed and merged on \`develop\`. No 1.x migration and no conflict ($(basename "$0")). No pin.

— Claude (lead, 2.0 build), by $(basename "$0")")"
  gh pr merge -R "$REPO" "$open" --auto --merge >/dev/null
fi
if [ -z "$open" ]; then
  echo "CATCH-UP OPEN: none yet (--dry-run: nothing opened)."
else
  echo "CATCH-UP OPEN $open (auto-merge, a merge commit)."
fi
