#!/usr/bin/env bash
# The tags image.yml pushes for this commit, from VERSION, GITHUB_REF and
# GITHUB_SHA (IMAGE: the image's name):
#   $IMAGE:main, $IMAGE:sha-<sha>   every push to main
#   $IMAGE:vX.Y.Z, $IMAGE:latest    the first build of a release's VERSION
#   $IMAGE:vX.Y.Z-beta.N            the first build of a 2.0 pre-release
#                                   (2.0 plan 7.4, B10a), and nothing else:
#                                   never :latest, :main or a moving tag, so
#                                   no one's update takes a beta
# A version tag is never overwritten. A beta is published only from its own
# branch, prerelease/vX.Y.Z-beta.N (release.yml's run there, which the
# owner's "release" starts): a push to main or a run started by hand on any
# other branch publishes none.
#
#   scripts/image-tags.sh >> "$GITHUB_OUTPUT"
#
# Prints tags= (comma-separated, maybe empty) and smoke= (the tag the smoke
# test runs, empty when nothing is pushed); refuses any other VERSION.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
: "${IMAGE:?IMAGE is not set}" "${GITHUB_REF:?GITHUB_REF is not set}" "${GITHUB_SHA:?GITHUB_SHA is not set}"
VERSION="v$(tr -d '[:space:]' < "$ROOT/VERSION")"

published() { docker buildx imagetools inspect "$IMAGE:$1" >/dev/null 2>&1; }

TAGS=() SMOKE=""
if [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  if [ "$GITHUB_REF" = "refs/heads/main" ]; then
    TAGS+=("$IMAGE:main" "$IMAGE:sha-${GITHUB_SHA::7}")
    SMOKE="$IMAGE:sha-${GITHUB_SHA::7}"
  fi
  if published "$VERSION"; then
    echo "$VERSION already published; not overwriting" >&2
  else
    TAGS+=("$IMAGE:$VERSION" "$IMAGE:latest")
    SMOKE="${SMOKE:-$IMAGE:$VERSION}"
    echo "publishing $VERSION" >&2
  fi
elif [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-beta\.[1-9][0-9]*$ ]]; then
  [ "$GITHUB_REF" = "refs/heads/prerelease/$VERSION" ] || {
    echo "VERSION $VERSION is a pre-release: only release.yml publishes it, from prerelease/$VERSION (this is $GITHUB_REF)" >&2
    exit 1
  }
  if published "$VERSION"; then
    echo "$VERSION already published; not overwriting" >&2
  else
    TAGS+=("$IMAGE:$VERSION")
    SMOKE="$IMAGE:$VERSION"
    echo "publishing the pre-release $VERSION (never :latest)" >&2
  fi
else
  echo "bad VERSION: $VERSION" >&2
  exit 1
fi

(IFS=,; echo "tags=${TAGS[*]-}")
echo "smoke=$SMOKE"
