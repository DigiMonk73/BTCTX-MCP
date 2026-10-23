#!/usr/bin/env bash
# What Start9 changed that BitcoinTX's StartOS package must follow
# (startos/UPDATING.md, "Watching Start9"; the owner, 2026-10-23: "we have to
# be aware when they push updates"). Each new thing opens one issue, labelled
# start9, so the owner is notified, and never a second one for the same thing
# (an issue with the same title, open or closed, counts):
#
#   - start-sdk on npm newer than develop's startos/package.json pins
#   - start-cli newer than develop's START_CLI_VERSION (CI and the release)
#   - a StartOS release: test BitcoinTX on it
#   - a start-registry release: check our start-cli still reads the registries
#   - Start9's packaging guide changed (the rules their reviewers hold us to),
#     or their shared package workflows (what builds the mirror and the fork)
#   - the latest build on the mirror or on Start9's fork failed
#   - Start9 changed their fork (template updates, SDK bumps): take it back
#
#   scripts/start9-watch.sh [--dry-run]
#
# --dry-run prints the issues it would open and opens none. Needs gh signed in
# (GH_TOKEN in CI), git, jq, npm and python3. Reads develop's pins from
# origin/develop (WATCH_REF overrides it): it fetches it first.
set -euo pipefail

DRY=false
[ "${1:-}" = "--dry-run" ] && DRY=true
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
REPO="${GITHUB_REPOSITORY:-DigiMonk73/BTCTX-MCP}"
REF="${WATCH_REF:-origin/develop}"
ST=Start9Labs/start-technologies
NOTES="https://github.com/$ST/releases/tag"
MIRROR=DigiMonk73/BTCTX-StartOS

git -C "$ROOT" fetch -q origin develop

# Opens an issue titled $1 with body $2, unless one with exactly that title
# exists, open or closed
open_once() {
  local title="$1" body="$2"
  if gh issue list -R "$REPO" --state all --limit 20 --search "in:title \"$title\"" \
      --json title --jq '.[].title' | grep -Fxq -- "$title"; then
    echo "already tracked: $title"
  elif $DRY; then
    printf 'WOULD OPEN: %s\n%s\n\n' "$title" "$body"
  else
    gh issue create -R "$REPO" --title "$title" --label start9 --body "$body"
  fi
}

# Whether version $2 is newer than $1 (leading v ignored)
newer() {
  local a="${1#v}" b="${2#v}"
  [ -n "$b" ] && [ "$a" != "$b" ] && [ "$(printf '%s\n%s\n' "$a" "$b" | sort -V | tail -1)" = "$b" ]
}

# The newest non-draft, non-prerelease release of one of Start9's projects
latest() {
  gh release list -R "$ST" --limit 100 --exclude-drafts --exclude-pre-releases \
    --json tagName --jq "[.[].tagName | select(startswith(\"$1/\"))][0] // \"\" | ltrimstr(\"$1/\")"
}

# Start of the window for "what changed": when the last issue titled $1 was
# opened, else 7 days ago (ISO 8601, UTC)
since() {
  local last
  last="$(gh issue list -R "$REPO" --state all --limit 20 --search "in:title \"$1\"" \
    --json createdAt --jq 'map(.createdAt) | max // empty')"
  [ -n "$last" ] && { echo "$last"; return; }
  python3 -c 'import datetime as d; print((d.datetime.now(d.timezone.utc) - d.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"))'
}

today() { python3 -c 'import datetime as d; print(d.datetime.now(d.timezone.utc).date())'; }

check_sdk() {
  local pinned latest_sdk
  pinned="$(git -C "$ROOT" show "$REF:startos/package.json" | jq -r '.dependencies["@start9labs/start-sdk"]')"
  latest_sdk="$(npm view @start9labs/start-sdk version)"
  echo "start-sdk: develop pins $pinned, npm has $latest_sdk"
  newer "$pinned" "$latest_sdk" || return 0
  read -r -d '' body <<EOF || true
npm has \`@start9labs/start-sdk\` $latest_sdk; \`develop\`'s \`startos/package.json\` pins $pinned.

- Read its release notes ($NOTES/start-sdk/v$latest_sdk; the npm package's own CHANGELOG can lag) for what it changes and its minimum StartOS.
- Start9's Pre-Publish Checklist requires the current SDK before any pull request to their fork: bump it before the next release (startos/UPDATING.md, "Bumping the SDK").
- First look at Start9's fork (\`scripts/start9-pull.sh --fork\`): if they bumped it there, take theirs with \`scripts/start9-pull.sh\`.
EOF
  open_once "start-sdk $latest_sdk is available" "$body"
}

check_start_cli() {
  local pinned latest_cli
  pinned="$(git -C "$ROOT" show "$REF:.github/workflows/ci.yml" | sed -n 's/^ *START_CLI_VERSION: *//p' | head -1)"
  latest_cli="$(latest start-cli)"
  latest_cli="${latest_cli#v}"
  pinned="${pinned#v}"
  echo "start-cli: develop's CI pins $pinned, Start9 released $latest_cli"
  newer "$pinned" "$latest_cli" || return 0
  read -r -d '' body <<EOF || true
Start9 released start-cli $latest_cli; \`develop\`'s CI and release pack \`btctx.s9pk\` with $pinned (\`START_CLI_VERSION\` in \`.github/workflows/ci.yml\` and \`release.yml\`). Start9's own builds pack with the newest.

Read its release notes ($NOTES/start-cli/v$latest_cli), check that a package it packs installs on the oldest StartOS the package supports (the lab VM), then bump \`START_CLI_VERSION\` and \`START_CLI_SHA256\` (\`start-cli_x86_64-linux\`) in both (startos/UPDATING.md, "Bumping the SDK", step 3). Tell Silas if the lab's own start-cli needs it (a Mac mini setup change).
EOF
  open_once "start-cli $latest_cli is available" "$body"
}

check_startos() {
  local v
  v="$(latest start-os)"
  echo "StartOS: latest release $v"
  [ -n "$v" ] || return 0
  read -r -d '' body <<EOF || true
Start9 released StartOS ${v#v} ($NOTES/start-os/$v). Users update to it, so BitcoinTX's package must work there:

- Read the release notes for anything that touches services: install and update, tasks and actions, backups, interfaces and networking, health checks.
- Update the lab VM (\`~/code/btctx-vm-lab\`: \`./vm.sh cli server update https://registry.start9.com --to ${v#v}\`, then restart it), then install the released package fresh and update to it from the previous release (\`docs/AGENT-TESTS.md\`, INS and UPG-1 to UPG-3), and record the result here.
- If it raises the minimum StartOS the SDK targets, the next package follows it (startos/UPDATING.md).
EOF
  open_once "StartOS ${v#v} is out: test BitcoinTX on it" "$body"
}

check_registry() {
  local v
  v="$(latest start-registry)"
  echo "start-registry: latest release $v"
  [ -n "$v" ] || return 0
  read -r -d '' body <<EOF || true
Start9 released start-registry ${v#v} ($NOTES/start-registry/$v), which serves the community registries. A new registry can need a newer start-cli to read it: on 2026-10-23, start-registry 1.2.0 made start-cli 2.4.1 and 2.4.2 fail on "registry package install" (icons as blake3 references); 2.5.0 reads it.

Check: \`start-cli -r https://community-registry.start9.com registry package get btctx short\` and the same for \`https://community-beta-registry.start9.com\`, with the lab's start-cli and with \`develop\`'s pinned one.
EOF
  open_once "start-registry ${v#v} is out: check that we can still read the community registries" "$body"
}

# Commits on Start9's repository at $1 (branch) under the paths $3...,
# since the last issue titled "$2 …", listed in one issue for today
check_commits() {
  local branch="$1" label="$2"
  shift 2
  local from list="" path
  from="$(since "$label")"
  for path in "$@"; do
    list+="$(gh api "repos/$ST/commits?sha=$branch&path=$path&since=$from&per_page=100" \
      --jq '.[] | "- [`\(.sha[0:8])`](\(.html_url)) \(.commit.committer.date[0:10]) \(.commit.message | split("\n")[0])"' || true)"$'\n'
  done
  list="$(printf '%s' "$list" | grep -v '^$' | awk '!seen[$0]++' || true)"
  echo "$label: $(printf '%s' "$list" | grep -c . || true) commit(s) since $from"
  [ -n "$list" ] || return 0
  read -r -d '' body <<EOF || true
Start9 changed these since $from (\`$ST\`, \`$branch\`):

$list

Read each against the StartOS package (\`startos/\`) and its docs; Start9's reviewers hold the package to the guide. If one changes what the package must do, file the change as an issue (or a pull request into \`staging\`), and keep the local copy current (\`git -C ~/code/start-technologies pull --ff-only\`).
EOF
  open_once "$label on $(today)" "$body"
}

# The latest completed run of each workflow on $1, opening an issue for a failure
check_builds() {
  local repo="$1"
  gh run list -R "$repo" --limit 30 --json databaseId,workflowName,status,conclusion,url,createdAt \
    --jq 'map(select(.status == "completed")) | group_by(.workflowName) | map(max_by(.createdAt))
          | .[] | "\(.workflowName)\t\(.conclusion)\t\(.databaseId)\t\(.url)"' |
  while IFS=$'\t' read -r name conclusion id url; do
    echo "$repo: $name: $conclusion"
    [ "$conclusion" = failure ] || continue
    read -r -d '' body <<EOF || true
The latest \`$name\` run on \`$repo\` failed: $url

On the mirror it builds and releases the package from Start9's shared workflows (\`$ST\`, \`.github/workflows/*.yml@master\`); on Start9's fork it publishes to their registries. Read the failed step: if it is Start9's shared workflow (as on 2026-10-23, \`qemu-user-static\` on Ubuntu 26.04), tell them on our open pull request to their fork, and the mirror's release can be published by hand (\`scripts/mirror-startos-release.sh\`); if it is ours, fix it here.
EOF
    open_once "Start9 build failed: $repo, $name (run $id)" "$body"
  done
}

check_fork() {
  local fork
  fork="$("$ROOT/scripts/start9-pull.sh" --fork 2>/dev/null | awk '{print $1}')"
  [ -n "$fork" ] || { echo "Start9's fork: none yet"; return 0; }
  check_builds "$fork"
  # --check reads the committed startos/ at HEAD: develop's, in a checkout of
  # its own, never switching the one this runs in
  local tree ok=false
  tree="$(mktemp -d)/develop"
  git -C "$ROOT" worktree add -q --detach "$tree" "$REF"
  "$tree/scripts/start9-pull.sh" --check >/dev/null 2>&1 && ok=true
  git -C "$ROOT" worktree remove --force "$tree"
  if $ok; then
    echo "Start9's fork: nothing to take back"
  else
    local head
    head="$(gh api "repos/$fork/commits/main" --jq '.sha[0:8]' 2>/dev/null || echo unknown)"
    read -r -d '' body <<EOF || true
Start9's fork has changes \`develop\`'s \`startos/\` doesn't (template updates, SDK bumps, review fixes). The next mirror sync and the release refuse to run until they're taken back: on a branch cut from \`staging\`, \`scripts/start9-pull.sh\` shows them and \`--apply\` takes them, then a pull request (startos/UPDATING.md, "After Start9 forks the mirror").
EOF
    open_once "Start9 changed their fork ($fork at $head): take it back" "$body"
  fi
}

check_sdk
check_start_cli
check_startos
check_registry
check_commits live-docs "Start9's packaging guide changed" projects/start-sdk/docs/src
check_commits master "Start9's shared package workflows changed" \
  .github/workflows/build.yml .github/workflows/tagAndRelease.yml .github/workflows/release.yml \
  .github/workflows/syncNext.yml .github/actions/setup-build-env
check_builds "$MIRROR"
check_fork
