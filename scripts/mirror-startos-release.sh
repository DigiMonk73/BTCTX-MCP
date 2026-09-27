#!/usr/bin/env bash
# Publish a BTCTX-MCP release's StartOS package on the mirror
# DigiMonk73/BTCTX-StartOS as well, so the mirror's releases page matches:
# one release per package version, on the tag sync-startos-mirror.sh created
# (v<upstream>_<revision>), titled v<upstream>:<revision>, marked Latest, with
# btctx.s9pk attached and the CHANGELOG notes. Run after the sync has pushed.
#
#   scripts/mirror-startos-release.sh SOURCE_TAG S9PK
#
# SOURCE_TAG  the BTCTX-MCP release tag (vX.Y.Z or vX.Y.Z-N)
# S9PK        path to that release's btctx.s9pk
# GH_TOKEN    must be able to write releases on the mirror (the workflow
#             passes MIRROR_TOKEN)
#
# Idempotent: an existing mirror release gets its notes and package replaced.
set -euo pipefail

SOURCE_TAG="$1"
S9PK="$2"
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REPO="${MIRROR_REPO:-DigiMonk73/BTCTX-StartOS}"
[ -f "$S9PK" ] || { echo "no package at $S9PK" >&2; exit 1; }

VERSION="$(sed -n "s/.*version: '\([0-9.]*:[0-9]*\)'.*/\1/p" "$ROOT/startos/startos/versions/current.ts" | head -1)"
[ -n "$VERSION" ] || { echo "can't read the package version from current.ts" >&2; exit 1; }
TAG="v${VERSION/:/_}"
gh api "repos/$REPO/git/ref/tags/$TAG" >/dev/null 2>&1 \
  || { echo "tag $TAG is not on $REPO; run sync-startos-mirror.sh --push first" >&2; exit 1; }

NOTES="$(mktemp)"
trap 'rm -f "$NOTES"' EXIT
awk -v tag="$SOURCE_TAG" '
  $0 ~ "^## \\[" tag "\\]" {on=1; next}
  on && /^## \[/ {exit}
  on {print}
' "$ROOT/docs/CHANGELOG.md" > "$NOTES"
[ -s "$NOTES" ] || { echo "no CHANGELOG section for $SOURCE_TAG" >&2; exit 1; }
cat >> "$NOTES" <<EOF

## Install

In StartOS, open **Sideload** and upload \`btctx.s9pk\`; installs of earlier versions update in place.

This repository mirrors \`startos/\` of [DigiMonk73/BTCTX-MCP](https://github.com/DigiMonk73/BTCTX-MCP), where the package is built: [BTCTX-MCP $SOURCE_TAG](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/$SOURCE_TAG). Image: \`ghcr.io/digimonk73/btctx-mcp:${SOURCE_TAG%-*}\`.
EOF

if gh release view "$TAG" -R "$REPO" >/dev/null 2>&1; then
  gh release edit "$TAG" -R "$REPO" --title "v$VERSION" --notes-file "$NOTES" --latest
  gh release upload "$TAG" -R "$REPO" --clobber "$S9PK"
  echo "Updated release $TAG on $REPO."
else
  gh release create "$TAG" -R "$REPO" --verify-tag --title "v$VERSION" --notes-file "$NOTES" --latest "$S9PK"
  echo "Created release $TAG on $REPO."
fi
