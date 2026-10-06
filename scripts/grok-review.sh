#!/usr/bin/env bash
# Grok's review of a pull request (AGENTS.md, "Reviews"): Grok Build reads the
# pull request in its own clone and prints its findings, for Claude to post on
# the pull request. Grok gets only read_file, list_dir and grep: no shell, no
# file writes, no web, so it can't change anything. Don't widen this: with a
# shell it inherits Claude's allow rules and ran a command it was told not to.
#
#   scripts/grok-review.sh <pull request number>
#
# GROK_CLONE  Grok's own clone of this repository, cloned on first use
#             (default ~/code/BTCTX-MCP-grok; never a clone anyone works in)
# GROK_MODEL  default grok-4.7, at its highest reasoning effort
set -euo pipefail

PR="${1:?usage: $0 <pull request number>}"
REPO=DigiMonk73/BTCTX-MCP
CLONE="${GROK_CLONE:-$HOME/code/BTCTX-MCP-grok}"
command -v grok >/dev/null || { echo "Grok Build (grok) isn't installed" >&2; exit 1; }

[ -d "$CLONE/.git" ] || git clone -q "https://github.com/$REPO.git" "$CLONE"
git -C "$CLONE" fetch -q origin "pull/$PR/head"
git -C "$CLONE" checkout -q --detach FETCH_HEAD

BRIEF="$(mktemp)"
trap 'rm -f "$BRIEF"' EXIT
{
  cat <<'EOF'
You are reviewing a pull request for BitcoinTX, a self-hosted Bitcoin portfolio and tax tracker. You did not write this change: review it skeptically, as an independent second reviewer. Claude wrote it; your job is to catch what it missed.

You can read any file in this checkout (the pull request's head). The project's rules are in AGENTS.md (CLAUDE.md before it), docs/CODE_STYLE.md and docs/MAINTENANCE.md. You can't run commands or reach the network, so judge from the code and the diff below, and say when a point needs checking by someone who can.

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
} > "$BRIEF"

cd "$CLONE"
grok --prompt-file "$BRIEF" -m "${GROK_MODEL:-grok-4.7}" --reasoning-effort xhigh \
  --tools read_file,list_dir,grep --disable-web-search --no-subagents --max-turns 40
