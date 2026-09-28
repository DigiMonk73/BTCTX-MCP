#!/usr/bin/env bash
# By hand, only when the mirror's own Tag and Release workflow (Start9's) can't
# run, e.g. before its DEV_KEY and REFERENCE_REGISTRY are set: publish a
# BTCTX-MCP release's StartOS package on the mirror DigiMonk73/BTCTX-StartOS,
# one release per package version, on the tag v<upstream>_<revision> (created
# on the mirror's main if missing), titled v<upstream>:<revision>, marked
# Latest, with btctx.s9pk attached and the CHANGELOG notes. Run after
# sync-startos-mirror.sh --push.
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
# Tag the sync commit of this version, not whatever main holds: the mirror's
# package version must be this one (sync-startos-mirror.sh --push first).
SHA="$(gh api "repos/$REPO/commits/main" --jq .sha)"
MIRROR_VERSION="$(gh api "repos/$REPO/contents/startos/versions/current.ts?ref=$SHA" --jq .content \
  | base64 -d | sed -n "s/.*version: '\([0-9.]*:[0-9]*\)'.*/\1/p" | head -1)"
[ "$MIRROR_VERSION" = "$VERSION" ] \
  || { echo "$REPO main is at ${MIRROR_VERSION:-?}, not $VERSION: run sync-startos-mirror.sh --push first" >&2; exit 1; }

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
  # Creating the tag also starts the mirror's own Release workflow, which
  # fails harmlessly without its DEV_KEY.
  gh release create "$TAG" -R "$REPO" --target "$SHA" --title "v$VERSION" --notes-file "$NOTES" --latest "$S9PK"
  echo "Created release $TAG on $REPO."
fi
