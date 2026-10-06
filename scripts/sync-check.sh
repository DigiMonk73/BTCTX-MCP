#!/usr/bin/env bash
# Is everything on this computer also on GitHub? One plain answer, for the
# owner and for the start and end of every session (AGENTS.md).
#
#   scripts/sync-check.sh [--tidy]      (make sync-check)
#
# Fetches from GitHub, then:
# - brings local main and develop up to GitHub's when they are only behind
#   (a fast-forward; not when checked out with changes, never when ahead);
# - lists what exists only here: changes not committed in any working
#   folder (the main checkout and every worktree), branches with commits
#   GitHub doesn't have (pushed, or in a merged pull request, counts as
#   on GitHub), stashes;
# - --tidy: also deletes the local branches whose work is on GitHub and that
#   no working folder has checked out, and forgets worktrees whose folder is
#   gone. It never removes a working folder: other sessions may be in them.
# Ends with "IN SYNC" (exit 0) or "NOT IN SYNC" and what to do (exit 1).
set -euo pipefail

TIDY=false
case "${1:-}" in "") ;; --tidy) TIDY=true ;; *) echo "usage: $0 [--tidy]" >&2; exit 2 ;; esac
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
g() { git -C "$ROOT" "$@"; }
REPO="$(g remote get-url origin | sed -E 's#(\.git)?/*$##; s#.*[:/]([^/]+/[^/]+)$#\1#')"
PROBLEMS=()

g fetch -q --prune origin || { echo "can't reach GitHub (git fetch failed): nothing checked" >&2; exit 1; }
$TIDY && g worktree prune

# "<path> <branch>" for every working folder ("-" for a detached HEAD).
worktrees() {
  g worktree list --porcelain | awk '
    /^worktree /{path=substr($0, 10)} /^branch /{sub("refs/heads/", "", $2); br=$2}
    /^detached/{br="-"} /^$/{if (path != "") print path "\t" br; path=""; br=""}
    END{if (path != "") print path "\t" br}'
}
checked_out() { worktrees | cut -f2 | grep -qxF "$1"; }
folder_of() { worktrees | awk -F'\t' -v b="$1" '$2 == b {print $1; exit}'; }

# Is <commit> on GitHub: on one of origin's branches, or inside a merged
# pull request of <branch> (GitHub deletes the branch after a squash merge)?
GH_FAILED=false
on_github() {
  local tip="$1" name="$2" n head prs
  [ -n "$(g for-each-ref --contains "$tip" refs/remotes/origin)" ] && return 0
  [ -n "$name" ] || return 1
  prs="$(gh pr list -R "$REPO" --state merged --head "$name" \
    --json number,headRefOid --jq '.[] | "\(.number) \(.headRefOid)"' 2>/dev/null)" || { GH_FAILED=true; return 1; }
  while read -r n head; do
    [ -n "$head" ] || continue
    [ "$head" = "$tip" ] && return 0
    g cat-file -e "$head^{commit}" 2>/dev/null || g fetch -q origin "pull/$n/head" 2>/dev/null || continue
    g merge-base --is-ancestor "$tip" "$head" && return 0
  done <<< "$prs"
  return 1
}

# main and develop: down from GitHub when only behind.
for b in main develop; do
  g rev-parse -q --verify "refs/heads/$b" >/dev/null || continue
  if ! g rev-parse -q --verify "refs/remotes/origin/$b" >/dev/null; then
    PROBLEMS+=("GitHub has no $b branch: local $b can't be compared")
    continue
  fi
  read -r ahead behind < <(g rev-list --left-right --count "$b...origin/$b")
  if [ "$ahead" -gt 0 ]; then
    PROBLEMS+=("local $b has $ahead commit(s) GitHub doesn't: never commit on $b (AGENTS.md, Branches)")
  elif [ "$behind" -gt 0 ]; then
    dir="$(folder_of "$b")"
    if [ -z "$dir" ]; then
      if g fetch -q origin "$b:$b"; then echo "$b: brought $behind commit(s) down from GitHub."
      else echo "$b: $behind commit(s) behind GitHub; bringing them down failed (see above)."; fi
    elif [ -z "$(git -C "$dir" status --porcelain --untracked-files=no 2>/dev/null)" ] \
      && git -C "$dir" merge -q --ff-only "origin/$b"; then
      echo "$b: brought $behind commit(s) down from GitHub ($dir)."
    else
      echo "$b: $behind commit(s) behind GitHub, not brought down: $dir has changes."
    fi
  fi
done

# Working folders: anything not committed, and a detached HEAD's commits.
echo "Working folders:"
while IFS=$'\t' read -r dir br; do
  if [ ! -d "$dir" ]; then
    echo "  ? $dir: folder gone (scripts/sync-check.sh --tidy forgets it)"
    continue
  fi
  if ! status="$(git -C "$dir" status --porcelain 2>/dev/null)"; then
    echo "  ✗ $dir: git can't read this folder"
    PROBLEMS+=("$dir: git can't read it (git -C \"$dir\" status says why)")
    continue
  fi
  changed=0; new=0  # a new symlink (e.g. a worktree's node_modules) isn't work
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    if [ "${line:0:3}" != "?? " ]; then changed=$((changed + 1))
    else f="${line:3}"; [ -L "$dir/${f%/}" ] || new=$((new + 1)); fi
  done <<< "$status"
  if [ "$changed$new" != 00 ]; then
    echo "  ✗ $dir ($br): $changed changed, $new new file(s), only here"
    PROBLEMS+=("$dir has work not committed: commit and push it, or throw it away")
  elif [ "$br" = - ] && ! on_github "$(git -C "$dir" rev-parse HEAD)" ""; then
    echo "  ✗ $dir (no branch): its commit isn't on GitHub"
    PROBLEMS+=("$dir has commits on no branch: put them on a branch and push it (git -C \"$dir\" switch -c <name>)")
  else
    echo "  ✓ $dir ($br): clean"
  fi
done < <(worktrees)

# Branches: commits only here; --tidy deletes the ones already on GitHub.
total=0; tidy=0; tidied=0
for b in $(g for-each-ref --format='%(refname:short)' refs/heads); do
  total=$((total + 1))
  [ "$b" = main ] || [ "$b" = develop ] && continue
  up="$(g for-each-ref --format='%(upstream:short)' "refs/heads/$b")"
  name="${up#origin/}"; name="${name:-$b}"
  if ! on_github "$(g rev-parse "$b")" "$name"; then
    PROBLEMS+=("branch $b has commits GitHub doesn't: push it (or delete it if it's not wanted)")
    continue
  fi
  checked_out "$b" && continue
  if $TIDY; then
    if g branch -q -D "$b"; then tidied=$((tidied + 1)); else echo "  couldn't delete $b (see above)"; fi
  else
    tidy=$((tidy + 1))
  fi
done
echo "Branches: $total here."
[ "$tidied" -gt 0 ] && echo "  Deleted $tidied whose work is on GitHub."
[ "$tidy" -gt 0 ] && echo "  $tidy are on GitHub already and could go: scripts/sync-check.sh --tidy"

$GH_FAILED && PROBLEMS+=("gh couldn't ask GitHub about merged pull requests (gh auth status): branches above may be on GitHub after all")

stashes="$(g stash list | wc -l | tr -d ' ')"
[ "$stashes" -gt 0 ] && PROBLEMS+=("$stashes stash(es), only here: git stash list")

echo
if [ "${#PROBLEMS[@]}" -eq 0 ]; then
  echo "IN SYNC: everything on this computer is on GitHub."
  exit 0
fi
echo "NOT IN SYNC: only on this computer:"
printf '  - %s\n' "${PROBLEMS[@]}"
exit 1
