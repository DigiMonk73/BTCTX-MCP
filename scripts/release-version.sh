#!/usr/bin/env bash
# Which version a release branch publishes (release.yml's first job), and
# whether the branch, VERSION, startos/startos/versions/current.ts and the
# CHANGELOG agree on it:
#
#   scripts/release-version.sh release/vX.Y.Z           a release, from main
#   scripts/release-version.sh release/vX.Y.Z-N         its package-only revision N
#   scripts/release-version.sh prerelease/vX.Y.Z-beta.N a 2.0 pre-release, from 2.0
#                                                       (2.0 plan 7.4, B10a)
#
# Prints, one per line: tag, version (vVERSION), revision (the package's),
# prerelease (true/false), base (the branch the commit must be on: main or
# 2.0) and connector (the version on PyPI, in PEP 440's form: X.Y.ZbN for a
# beta). Each value is a plain word, so the lines can be sourced. Anything
# that disagrees is refused on stderr, with nothing printed.
#
# A release's VERSION is X.Y.Z, a pre-release's X.Y.Z-beta.N (N from 1). A
# beta takes no package-only revision: a fix is the next beta.
set -euo pipefail

BRANCH="${1:?usage: scripts/release-version.sh release/vX.Y.Z | prerelease/vX.Y.Z-beta.N}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RELEASE='[0-9]+\.[0-9]+\.[0-9]+'
BETA="$RELEASE-beta\.[1-9][0-9]*"

fail() { echo "$*" >&2; exit 1; }

VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
[[ "$VERSION" =~ ^[0-9A-Za-z.-]+$ ]] || fail "VERSION $VERSION is not X.Y.Z"
CURRENT="$ROOT/startos/startos/versions/current.ts"
REVISION="$(sed -n "s/.*version: '${VERSION//./\\.}:\([0-9][0-9]*\)'.*/\1/p" "$CURRENT")"
[ -n "$REVISION" ] || fail "startos/startos/versions/current.ts is not $VERSION:<n>"

case "$BRANCH" in
  release/*)
    TAG="${BRANCH#release/}" PRERELEASE=false BASE=main
    [[ "$VERSION" =~ ^$BETA$ ]] && fail "VERSION $VERSION is a pre-release: publish it from prerelease/v$VERSION"
    [[ "$VERSION" =~ ^$RELEASE$ ]] || fail "VERSION $VERSION is not X.Y.Z"
    CONNECTOR="$VERSION"
    # vX.Y.Z for package revision 0; vX.Y.Z-N for a package-only revision N
    if [ "$REVISION" = 0 ]; then EXPECTED="v$VERSION"; else EXPECTED="v$VERSION-$REVISION"; fi
    ;;
  prerelease/*)
    TAG="${BRANCH#prerelease/}" PRERELEASE=true BASE=2.0
    [[ "$VERSION" =~ ^$BETA$ ]] || fail "VERSION $VERSION is not a beta (X.Y.Z-beta.N): a release is published from release/"
    [ "$REVISION" = 0 ] || fail "current.ts says $VERSION:$REVISION: a beta takes no package revision, a fix is the next beta"
    CONNECTOR="${VERSION%-beta.*}b${VERSION##*-beta.}"
    EXPECTED="v$VERSION"
    ;;
  *) fail "branch $BRANCH is neither release/ nor prerelease/" ;;
esac
[ "$TAG" = "$EXPECTED" ] || fail "branch $BRANCH: VERSION and current.ts say $EXPECTED"
grep -q "^## \[$TAG\]" "$ROOT/docs/CHANGELOG.md" || fail "no CHANGELOG section for $TAG"

printf '%s\n' "tag=$TAG" "version=v$VERSION" "revision=$REVISION" "prerelease=$PRERELEASE" \
  "base=$BASE" "connector=$CONNECTOR"
