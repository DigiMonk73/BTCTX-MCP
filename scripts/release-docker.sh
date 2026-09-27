#!/usr/bin/env bash
#
# release-docker.sh — build and push the BitcoinTX Docker image for a release.
#
# Enforces the Docker Tag Contract that the StartOS wrapper
# (DigiMonk73/BTCTX-StartOS) depends on — see docs/STARTOS_COMPATIBILITY.md,
# "Docker Tag Contract":
#   1. Version tag matches ^v[0-9]+\.[0-9]+\.[0-9]+$ exactly (no -rc/-beta)
#   2. Version tags are immutable — refuses to overwrite an existing Hub tag
#   3. Multi-arch manifest list: linux/amd64 + linux/arm64
#   4. :latest is pushed alongside, never alone
#
# Usage: ./scripts/release-docker.sh vX.Y.Z
#   Run from the repo root, after tagging the release in git.

set -euo pipefail

IMAGE="b1ackswan/btctx"
VERSION="${1:-}"

if [[ -z "$VERSION" ]]; then
    echo "Usage: $0 vX.Y.Z (e.g. $0 v0.6.0)" >&2
    exit 1
fi

# Contract 1: exact semver tag, no pre-release suffixes. The wrapper's daily
# release-detection job only recognizes this pattern.
if ! [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "ERROR: '$VERSION' does not match ^v[0-9]+\.[0-9]+\.[0-9]+\$" >&2
    echo "The StartOS wrapper pins exact vX.Y.Z tags; -rc/-beta suffixes are not allowed on Docker tags." >&2
    exit 1
fi

# The Docker tag must correspond to a real git release tag.
if ! git rev-parse -q --verify "refs/tags/$VERSION" >/dev/null; then
    echo "ERROR: git tag '$VERSION' does not exist. Tag the release first." >&2
    exit 1
fi

# Contract 2: immutability. The wrapper's reproducible builds assume a version
# tag always resolves to the same image. If a build needs fixing, cut a new
# patch version instead.
HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' \
    "https://hub.docker.com/v2/repositories/${IMAGE}/tags/${VERSION}")
if [[ "$HTTP_CODE" == "200" ]]; then
    echo "ERROR: ${IMAGE}:${VERSION} already exists on Docker Hub." >&2
    echo "Version tags are immutable — cut a new patch version instead of re-pushing." >&2
    exit 1
elif [[ "$HTTP_CODE" != "404" ]]; then
    echo "ERROR: could not check Docker Hub for ${IMAGE}:${VERSION} (HTTP $HTTP_CODE)." >&2
    exit 1
fi

# Contracts 3 + 4: single multi-arch manifest list, version tag + latest together.
echo "Building and pushing ${IMAGE}:${VERSION} + ${IMAGE}:latest (linux/amd64, linux/arm64)..."
docker buildx build --platform linux/amd64,linux/arm64 \
    -t "${IMAGE}:${VERSION}" \
    -t "${IMAGE}:latest" \
    --push .

echo
echo "Verifying pushed manifest..."
docker buildx imagetools inspect "${IMAGE}:${VERSION}" | grep -E 'Name:|Platform:'

echo
echo "Done. ${IMAGE}:${VERSION} and ${IMAGE}:latest are live on Docker Hub."
