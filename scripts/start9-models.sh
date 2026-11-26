#!/usr/bin/env bash
# Print the `model:` line a pull request to Start9's fork needs: Start9's
# publishing.md, "The Pipeline" (2026-11-26), has its description name, on a
# line of its own, each AI model that wrote any of it, by the id its harness
# reports (`model: claude-opus-5-5`), comma-separated; Start9 picks the AI
# reviewer from it. The mirror's commits carry no co-authors, so the models
# come from this repository's commits that changed startos/ and are in the
# pull request: their Co-Authored-By lines, one id each.
#
#   scripts/start9-models.sh SINCE [UNTIL]
#
# SINCE  the commit (or tag) Start9 already has: the last release they merged
# UNTIL  the commit sent (default HEAD)
#
# Prints nothing when no AI model co-wrote those commits. A Claude co-author
# ("Claude Opus 5.5 <noreply@anthropic.com>") becomes its id
# (claude-opus-5-5); any other co-author is named on stderr for a person to
# decide, and left out.
set -euo pipefail

[ $# -ge 1 ] && [ $# -le 2 ] || { echo "usage: $0 SINCE [UNTIL]" >&2; exit 2; }
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

ids=()
while IFS= read -r author; do
  [ -n "$author" ] || continue
  case "$author" in
    *"<noreply@anthropic.com>")
      # "Claude Opus 5.5" -> "claude-opus-5-5", as the harness names it.
      ids+=("$(printf '%s' "${author% <*}" | tr '[:upper:]' '[:lower:]' | tr ' .' '--')") ;;
    *) echo "Not a model this script knows, left out of the model: line: $author" >&2 ;;
  esac
done < <(git -C "$ROOT" log --format='%(trailers:key=Co-Authored-By,valueonly,unfold)' "$1..${2:-HEAD}" -- startos/)

[ ${#ids[@]} -gt 0 ] || exit 0
printf 'model: %s\n' "$(printf '%s\n' "${ids[@]}" | sort -u | paste -sd, - | sed 's/,/, /g')"
