#!/usr/bin/env bash
# Print the `model:` line a pull request to Start9's fork needs: Start9's
# publishing.md, "The Pipeline" (2026-11-26), has its description name, on a
# line of its own, each AI model that wrote any of it, by the id its harness
# reports (`model: claude-opus-5-5`), comma-separated; Start9 picks the AI
# reviewer from it. The mirror's commits carry no co-authors, so the models
# come from this repository's commits that changed startos/ and are in the
# pull request: their Co-Authored-By lines, one id each.
#
#   scripts/start9-models.sh [SINCE [UNTIL]]
#
# SINCE  the commit Start9 already has; default, or --fork: the newest commit
#        of ours their fork holds (its newest "Sync from DigiMonk73/BTCTX-MCP@…",
#        which our mirror sync writes), found with start9-pull.sh --fork
# UNTIL  the commit sent (default HEAD)
#
# Prints nothing when no AI model co-wrote those commits. A Claude co-author
# ("Claude Opus 5.5 <noreply@anthropic.com>") becomes its id
# (claude-opus-5-5); any other co-author, or a Claude name that gives no
# model id, is named on stderr for a person to decide, and left out.
#
# START9_FORK, START9_BRANCH, FORK_URL  their fork, as for start9-pull.sh
set -euo pipefail

[ $# -le 2 ] || { echo "usage: $0 [SINCE|--fork [UNTIL]]" >&2; exit 2; }
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SINCE="${1---fork}"   # given but empty is refused below, never the default
UNTIL="${2-HEAD}"

commit_of() {  # the full id of a commit here, or nothing
  git -C "$ROOT" rev-parse -q --verify "$1^{commit}" 2>/dev/null || true
}

if [ "$SINCE" = --fork ]; then
  if [ -z "${START9_FORK:-}" ]; then
    read -r START9_FORK START9_BRANCH <<< "$("$ROOT/scripts/start9-pull.sh" --fork)" || true
  fi
  [ -n "${START9_FORK:-}" ] || { echo "Start9 hasn't forked the mirror yet: no pull request to name models for." >&2; exit 1; }
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  git init -q --bare "$TMP/fork"
  git -C "$TMP/fork" fetch -q "${FORK_URL:-https://github.com/$START9_FORK.git}" "${START9_BRANCH:?START9_BRANCH}" \
    || { echo "can't fetch $START9_FORK ($START9_BRANCH)" >&2; exit 1; }
  # Every sync of ours they hold, also inside a squash's message; the newest
  # one here is what they have.
  messages="$(git -C "$TMP/fork" log --format=%B FETCH_HEAD)"
  best="" best_count=-1
  for short in $(printf '%s\n' "$messages" | grep -o 'Sync from DigiMonk73/BTCTX-MCP@[0-9a-f]\{7,40\}' | sed 's/.*@//' | sort -u || true); do
    full="$(commit_of "$short")"
    [ -n "$full" ] || continue
    count="$(git -C "$ROOT" rev-list --count "$full")"
    if [ "$count" -gt "$best_count" ]; then best="$full" best_count="$count"; fi
  done
  [ -n "$best" ] || { echo "can't tell which of our commits $START9_FORK holds: give SINCE" >&2; exit 1; }
  SINCE="$best"
fi
for rev in "$SINCE" "$UNTIL"; do
  [ -n "$(commit_of "$rev")" ] || { echo "not a commit here: '$rev'" >&2; exit 2; }
done

# Every Co-Authored-By line in the messages, not only the last trailer block:
# a squash's message carries each commit's own lines in its middle.
log="$(git -C "$ROOT" log --format=%B "$SINCE..$UNTIL" -- startos/)"
authors="$(printf '%s\n' "$log" | tr -d '\r' \
  | awk 'tolower($0) ~ /^[ \t]*co-authored-by:/ { sub(/^[^:]*:[ \t]*/, ""); print }' | sort -u)"

ids=()
while IFS= read -r author; do
  [ -n "$author" ] || continue
  case "$author" in
    *"<noreply@anthropic.com>")
      # "Claude Opus 5.5" -> "claude-opus-5-5", as the harness names it; a
      # note after the name ("(1M context)") isn't part of the id.
      name="$(printf '%s' "${author% <*}" | sed -E 's/ *[([].*$//')"
      id="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]' | tr ' .' '--')"
      if printf '%s' "$id" | grep -Eq '^claude(-[a-z0-9]+)+$' && printf '%s' "$id" | grep -q '[0-9]'; then
        ids+=("$id")
      else
        echo "A Claude co-author with no model id, left out of the model: line: $author" >&2
      fi ;;
    *) echo "Not a model this script knows, left out of the model: line: $author" >&2 ;;
  esac
done <<< "$authors"

[ ${#ids[@]} -gt 0 ] || exit 0
printf 'model: %s\n' "$(printf '%s\n' "${ids[@]}" | sort -u | paste -sd, - | sed 's/,/, /g')"
