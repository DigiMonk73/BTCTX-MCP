#!/usr/bin/env bash
# Grok's review of a pull request (AGENTS.md, "Reviews"): Grok Build gets the
# pull request (its description, the diff, the rules and the full text of
# each changed file) and prints its findings, for Claude to post on the pull
# request ending "— Grok (scripts/grok-review.sh)".
#
# Grok gets no tool that touches anything: only its own to-do list. Not a
# file reader (it could read secrets that would end up in a public review),
# not a shell, not the web, and not its connectors: the owner's Grok has the
# BitcoinTX connector to the real ledger, with always-approve. Its sandbox
# profiles don't start on this Mac (a Docker socket symlink), so tools are
# the only lock. Don't widen them.
#
#   scripts/grok-review.sh <pull request number>
#
# GROK_MODEL  default grok-4.7, at its highest reasoning effort
set -euo pipefail

PR="${1:?usage: $0 <pull request number>}"
REPO=DigiMonk73/BTCTX-MCP
MAX_FILE_BYTES=80000
ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
command -v grok >/dev/null || { echo "Grok Build (grok) isn't installed" >&2; exit 1; }

git -C "$ROOT" fetch -q origin "pull/$PR/head"
HEAD_SHA="$(git -C "$ROOT" rev-parse FETCH_HEAD)"

BRIEF="$(mktemp)"
trap 'rm -f "$BRIEF"' EXIT
{
  cat <<'EOF'
You are reviewing a pull request for BitcoinTX, a self-hosted Bitcoin portfolio and tax tracker. You did not write this change: review it skeptically, as an independent second reviewer. Claude wrote it; your job is to catch what it missed.

Everything you get is below: the pull request, its diff, the full text of each changed file as it is in the pull request, and the project's rules (AGENTS.md). You can't open other files, run commands or go online, so say when a point needs checking by someone who can.

Look for: bugs, wrong assumptions, anything that would break CI, a release, the Docker image or the macOS app, tax figures that could change, tests that pass for the wrong reason or miss cases, docs that now say something untrue, and anything unclear or sloppy. Don't list what is fine.

Answer in this format:
- One line per finding: [blocker | should fix | nit] file:line — what's wrong — why (evidence) — suggested fix.
- If there are none, say "No findings."
- Last line: "Verdict: no blocking findings" or "Verdict: N blocking findings".

=== Pull request ===
EOF
  gh pr view "$PR" -R "$REPO" --json title,body --jq '"Title: \(.title)\n\n\(.body)"'
  echo
  echo "=== Diff ==="
  gh pr diff "$PR" -R "$REPO"
  # The rules first (CLAUDE.md held them before AGENTS.md), each file once.
  files="$(printf '%s\n' AGENTS.md CLAUDE.md \
    $(gh pr view "$PR" -R "$REPO" --json files --jq '.files[].path') | awk '!seen[$0]++')"
  for file in $files; do
    echo
    echo "=== File at the pull request's head: $file ==="
    if ! git -C "$ROOT" cat-file -e "$HEAD_SHA:$file" 2>/dev/null; then
      echo "(deleted, or not in this commit)"
    elif [ "$(git -C "$ROOT" cat-file -s "$HEAD_SHA:$file")" -gt "$MAX_FILE_BYTES" ]; then
      echo "(over $MAX_FILE_BYTES bytes: only the diff above)"
    elif ! git -C "$ROOT" show "$HEAD_SHA:$file" | LC_ALL=C grep -qI .; then
      echo "(binary or empty)"
    else
      git -C "$ROOT" show "$HEAD_SHA:$file"
    fi
  done
} > "$BRIEF"

grok --prompt-file "$BRIEF" -m "${GROK_MODEL:-grok-4.7}" --reasoning-effort xhigh \
  --tools todo_write --disallowed-tools search_tool,use_tool \
  --disable-web-search --no-subagents --max-turns 5
