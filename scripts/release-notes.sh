#!/usr/bin/env bash
# The notes of a release, from its "## [<tag>]" section of docs/CHANGELOG.md.
# A section that opens with a summary (text before its first "### " heading,
# as v1.2.9's does) gives only that summary and a link to the whole section:
# GitHub refuses a release body over 125,000 characters, and v1.2.9's section
# alone is longer. A section without one gives the whole section.
#
#   scripts/release-notes.sh vX.Y.Z > notes.md
#
# Refuses notes over 120,000 bytes, which leaves room for what the caller adds
# (release.yml's Downloads list). release.yml runs it in its first job, so too
# long a section stops the release before anything is published (the PyPI job
# runs before the release itself is created). mirror-startos-release.sh uses it
# too.
set -euo pipefail

TAG="${1:?usage: scripts/release-notes.sh vX.Y.Z}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LIMIT=120000

SECTION="$(awk -v tag="$TAG" '
  $0 ~ "^## \\[" tag "\\]" {on=1; next}
  on && /^## \[/ {exit}
  on {print}
' "$ROOT/docs/CHANGELOG.md")"
[ -n "$(printf '%s' "$SECTION" | tr -d '[:space:]')" ] \
  || { echo "no CHANGELOG section for $TAG" >&2; exit 1; }

# awk reads to the end: an early exit would stop printf with SIGPIPE.
SUMMARY="$(printf '%s\n' "$SECTION" | awk '/^### /{done=1} !done {print}')"
if [ -n "$(printf '%s' "$SUMMARY" | tr -d '[:space:]')" ]; then
  NOTES="$(printf '%s\n\nEvery change in %s, in detail: [docs/CHANGELOG.md](https://github.com/DigiMonk73/BTCTX-MCP/blob/%s/docs/CHANGELOG.md)' \
    "$SUMMARY" "$TAG" "$TAG")"
else
  NOTES="$SECTION"
fi

SIZE="$(printf '%s\n' "$NOTES" | wc -c | tr -d ' ')"
[ "$SIZE" -le "$LIMIT" ] || {
  echo "the notes for $TAG are $SIZE bytes, over $LIMIT: GitHub refuses a release body over 125,000 characters. Give the section a shorter summary before its first ### heading." >&2
  exit 1
}
printf '%s\n' "$NOTES"
