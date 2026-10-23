#!/usr/bin/env bash
# Keep the 2.0 build up to date with develop (AGENTS.md, "Branches"; plan:
# docs/temp/2.0-accounts.md 7.2, point 2; the owner's decision 24 on #251).
# The build's lead runs it before every 2.0 step and nightly.
#
#   scripts/catch-up-2.0.sh [--dry-run]      (make catch-up-2.0 [ARGS=--dry-run])
#
# Fetches from GitHub; when develop has commits 2.0 lacks:
# - stops for the lead ("needs the lead:", nothing opened) on what a clean
#   merge can't take: a 1.x migration (2.0's migrations go after it), the
#   reference test ledger or its figures changed (B1's reference_1x.db is
#   made again), or a conflict;
# - else has GitHub make the merge (2.0 first, then develop) on a branch of
#   its own, 2.0-merge-develop-auto-<date>-<develop>, opens its pull request
#   and turns on auto-merge as a merge commit for that very commit: its own
#   CI tests it before it lands, and a later develop commit waits for the
#   next run. Nothing while a 2.0 step has auto-merge on (its pin must stay
#   2.0's tip, and a merge made now would land on a 2.0 its CI never saw).
#   One already open is named, never changed: its auto-merge is the lead's.
# - lists what the lead does next ("to do:"): a new 1.x release (reference_1x.db
#   made again from it), changes under startos/ (for 2.0's package step, B9).
# Ends with one line: UP TO DATE, CATCH-UP OPEN <url>, CATCH-UP OPENED <url>,
# CATCH-UP WAITS, DRY RUN, or NEEDS THE LEAD; exit 0, 1 when the lead must
# step in, 2 when it can't tell (CAN'T TELL, on stderr).
set -euo pipefail

DRY=false
case "${1:-}" in "") ;; --dry-run) DRY=true ;; *) echo "usage: $0 [--dry-run]" >&2; exit 2 ;; esac
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
g() { git -C "$ROOT" "$@"; }
REPO="$(g remote get-url origin | sed -E 's#(\.git)?/*$##; s#.*[:/]([^/]+/[^/]+)$#\1#')"
OURS=origin/2.0 THEIRS=origin/develop
FIXTURE_SCRIPT=backend/tests/fixtures/make_reference_1x_db.py
REFERENCE=(testdata/reference_ledger.json testdata/reference_figures.json)
AUTO=2.0-merge-develop-auto-

unsure() { echo "CAN'T TELL: $1" >&2; exit 2; }

g fetch -q origin develop 2.0 '+refs/tags/v*:refs/tags/v*' || unsure "git fetch failed: nothing checked"
g rev-parse -q --verify "$OURS" >/dev/null && g rev-parse -q --verify "$THEIRS" >/dev/null \
  || unsure "GitHub has no 2.0 or no develop branch"

TODO=() STOPS=()

# A 1.x release newer than the one B1's upgraded-1.x ledger was saved by
released="$(g tag -l 'v1.*' --sort=-v:refname | grep -E '^v1\.[0-9]+\.[0-9]+$' | head -1 || true)"
fixture="$(g show "$OURS:$FIXTURE_SCRIPT" 2>/dev/null | sed -nE 's/^RELEASE = "(v[0-9.]+)"$/\1/p' || true)"
if [ -n "$released" ] && [ -n "$fixture" ] && [ "$released" != "$fixture" ] \
   && [ "$(printf '%s\n%s\n' "$released" "$fixture" | sort -V | tail -1)" = "$released" ]; then
  TODO+=("$released is out: make reference_1x.db again from it ($FIXTURE_SCRIPT --release $released) by a pull request into 2.0")
fi

# 2.0's open pull requests: number, url, branch, head commit, auto-merge on, from a fork
prs="$(gh pr list -R "$REPO" --base 2.0 --state open --limit 100 \
  --json number,url,headRefName,headRefOid,autoMergeRequest,isCrossRepository \
  --jq '.[] | [.number, .url, .headRefName, .headRefOid, (.autoMergeRequest != null), .isCrossRepository] | @tsv')" \
  || unsure "gh can't list 2.0's pull requests: nothing opened"
catch_up="" catch_up_auto="" stepping=""
while IFS=$'\t' read -r number url branch head auto fork; do
  [ -n "$number" ] && [ "$fork" = false ] || continue
  if [[ "$branch" == 2.0-merge-develop* ]]; then
    catch_up="$url" catch_up_auto="$auto"
  elif [ "$auto" = true ]; then
    stepping="${stepping:+$stepping, }#$number"
  fi
done <<< "$prs"

say_todos() { for item in "${TODO[@]+"${TODO[@]}"}"; do echo "to do: $item"; done; }

behind="$(g rev-list --count --no-merges "$OURS..$THEIRS")"
if [ "$behind" = 0 ]; then
  say_todos
  echo "UP TO DATE: 2.0 has everything on develop."
  exit 0
fi
echo "develop has $behind commit(s) 2.0 lacks:"
g log --oneline --no-merges "$OURS..$THEIRS" | sed 's/^/  /'

base="$(g merge-base "$OURS" "$THEIRS")" || unsure "git can't find where 2.0 and develop meet"
changed="$(g diff --name-only --no-renames "$base" "$THEIRS")" || unsure "git can't list what develop changed"
migrations="$(echo "$changed" | grep -E '^backend/migrations/versions/.*\.py$' || true)"
[ -z "$migrations" ] || STOPS+=("a 1.x migration ($(echo "$migrations" | xargs -n1 basename | tr '\n' ' ' | sed 's/ $//')): merge develop in a 2.0-merge-develop branch and put 2.0's migrations after it (0100 re-pointed until beta.1 is out, then a merge revision: #251 says which; 7.2, point 2)")
reference="$(echo "$changed" | grep -Fx -e "${REFERENCE[0]}" -e "${REFERENCE[1]}" || true)"
[ -z "$reference" ] || STOPS+=("the reference test ledger or its figures changed: merge develop in a 2.0-merge-develop branch and make reference_1x.db and its figures again ($FIXTURE_SCRIPT)")
set +e
g merge-tree --write-tree --quiet "$OURS" "$THEIRS" >/dev/null 2>&1
merged=$?
set -e
case "$merged" in
  0) ;;
  1) STOPS+=("the merge conflicts: merge develop in a 2.0-merge-develop branch and resolve it there") ;;
  *) unsure "git merge-tree failed (exit $merged): can't tell whether the merge is clean" ;;
esac
startos="$(echo "$changed" | grep -c '^startos/' || true)"
[ "$startos" = 0 ] || TODO+=("$startos file(s) under startos/ changed (SDK, start-cli, the package): note them on #251 for 2.0's package step (B9)")
say_todos

if [ ${#STOPS[@]} -gt 0 ]; then
  for item in "${STOPS[@]}"; do echo "needs the lead: $item"; done
  [ -z "$catch_up" ] || echo "open catch-up: $catch_up (it may be an earlier develop's, or the lead's own)"
  echo "NEEDS THE LEAD: nothing opened."
  exit 1
fi

if [ -n "$catch_up" ]; then
  # It lands first (an earlier develop's), and the next run takes the rest
  [ "$catch_up_auto" = true ] && [ -n "$stepping" ] \
    && echo "to do: a 2.0 step ($stepping) and this catch-up both have auto-merge on: the step's pin may no longer be 2.0's tip when it lands"
  [ "$catch_up_auto" = true ] \
    || echo "to do: the catch-up's auto-merge is off (turned off, red, or behind a step): the lead's call"
  echo "CATCH-UP OPEN $catch_up (auto-merge $([ "$catch_up_auto" = true ] && echo on || echo off))."
  exit 0
fi
if [ -n "$stepping" ]; then
  echo "to do: a 2.0 step ($stepping) has auto-merge on: the catch-up waits for it (the next run makes it on the new 2.0)"
  echo "CATCH-UP WAITS: nothing opened."
  exit 0
fi
if $DRY; then
  echo "DRY RUN: a catch-up would be opened now; nothing opened."
  exit 0
fi
develop="$(g rev-parse "$THEIRS")"
branch="$AUTO$(date +%Y%m%d)-${develop:0:7}"
forget_branch() { gh api -X DELETE "repos/$REPO/git/refs/heads/$branch" >/dev/null 2>&1 || true; }
gh api -X POST "repos/$REPO/git/refs" -f ref="refs/heads/$branch" -f sha="$(g rev-parse "$OURS")" >/dev/null \
  || unsure "GitHub couldn't make the branch $branch (one of that name may be left from an earlier run today, with no pull request: the lead deletes it)"
commit="$(gh api -X POST "repos/$REPO/merges" -f base="$branch" -f head="$develop" \
  -f commit_message="Merge develop into 2.0 ($(date +%Y-%m-%d))

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" --jq '.sha')" || commit=""
if [ -z "$commit" ]; then
  forget_branch
  unsure "GitHub couldn't make the merge on $branch (the branch is removed again)"
fi
pr_body() {
  cat <<EOF
## What and why

\`develop\` into \`2.0\` (\`docs/temp/2.0-accounts.md\` 7.2, point 2), a merge commit GitHub made of \`2.0\` (first) and \`develop\` ${develop:0:7}, merged with a merge commit, never a squash. Every change in it was reviewed and merged on \`develop\`. Checked by \`scripts/catch-up-2.0.sh\`: no 1.x migration, no change to the reference test ledger or its figures, no conflict. So, by the owner's decision 24 (#251), it merges once its own CI passes, with no review of its own. No pin.

## In plain words

1.x's latest fixes come into the 2.0 branch.

## How it was tested

This pull request's own CI, on this merge commit (auto-merge is set for it alone).

## Risk

What \`develop\` already carries, reviewed there.

- [x] Every change reviewed and merged on \`develop\`; none is new here
- [x] No 1.x migration, no change to the reference test ledger, no conflict (checked by the script)

— Claude (lead, 2.0 build), by scripts/catch-up-2.0.sh
EOF
}
url="$(pr_body | gh pr create -R "$REPO" --base 2.0 --head "$branch" --title "develop into 2.0, $(date +%Y-%m-%d)" --body-file -)" \
  || { forget_branch; unsure "gh couldn't open the pull request for $branch (the branch is removed again)"; }
gh pr merge -R "$REPO" "$url" --auto --merge --match-head-commit "$commit" >/dev/null \
  || unsure "gh couldn't turn on auto-merge for $url: it is open without it"
echo "CATCH-UP OPENED $url (auto-merge on)."
