#!/usr/bin/env bash
# The Monday report (docs/MAINTENANCE.md, "The Monday report"; the owner,
# 2026-10-31: after 2.0, routine checks run on GitHub, not on a Mac or on
# Claude's tokens). One issue, opened if none is open and edited in place
# otherwise, that lists what needs attention:
#
#   - open tax-figures issues, with who has each
#   - outside reports with no answer: issues opened by anyone but the owner or
#     a bot, with no comment from the owner, here, on Start9's fork and on the
#     mirror (whose Issues are off: the report says if that changes). An answer
#     is promised within a week; older ones are marked.
#   - open start9 issues (what start9-watch.sh opened and nobody has taken)
#
# It says nothing about security advisories, not even how many: a public
# count would hint at a problem that isn't fixed yet (SECURITY.md).
#
#   scripts/monday-report.sh [--dry-run]
#
# --dry-run prints the report and what it would do, and changes nothing. Needs
# gh signed in (GH_TOKEN in CI), jq and bash 3.2 or later. Only reads public
# data from other repositories, with REST calls any token can make. Exits 1
# after publishing when a repository couldn't be read.
set -euo pipefail

DRY=false
case "${1:-}" in
  "") ;;
  --dry-run) DRY=true ;;
  *) echo "usage: scripts/monday-report.sh [--dry-run]" >&2; exit 2 ;;
esac
REPO="${GITHUB_REPOSITORY:-DigiMonk73/BTCTX-MCP}"
OWNER="${REPO%%/*}"
FORK="${START9_FORK:-Start9-Community/BTCTX-StartOS}"   # as release.yml finds the fork
MIRROR=DigiMonk73/BTCTX-StartOS
TITLE="Monday report: what needs attention"
NOW="$(date -u +%s)"

if [ -n "${GITHUB_ACTIONS:-}" ]; then
  SIGNED="— the Monday report (GitHub Actions)"
else
  SIGNED="— Claude (scripts/monday-report.sh)"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
SECTIONS="$TMP/sections.md"
BODY="$TMP/body.md"
: >"$SECTIONS"
ITEMS=0     # entries listed, over all the sections
FAILED=0    # repositories that couldn't be read

# jq helpers. A title is someone else's text, so it goes in a code span, where
# nothing is a link, a mention or an issue reference: its backticks, control
# characters and text-direction marks are taken out, and it's cut to 100.
DEFS='
def safe: gsub("[[:cntrl:]`‪-‮⁦-⁩]"; " ") | .[0:100];
def seconds: $now - (.createdAt | fromdateiso8601);
def days: (seconds / 86400 | floor) as $d | if $d == 0 then "today" elif $d == 1 then "1 day" else "\($d) days" end;
def entry(note): "- [#\(.number)](\(.url)) `\(.title | safe)`, \(days)\(note)";
def listed(note): (.[0:50] | map(entry(note))) + (if length > 50 then ["- … and \(length - 50) more"] else [] end) | .[];
def who: . as $i | [ (select(any($i.labels[]; . == "claude")) | "Claude"), (select(any($i.labels[]; . == "owner")) | "the owner") ]
  | if length == 0 then "nobody has it" else join(" and ") + (if length == 1 then " has it" else " have it" end) end;
'

# Open issues of $1 ($2: only those with this label) as JSON, the same shape
# whoever's they are: pull requests left out, a bot told by its account type
open_issues() {
  local query="repos/$1/issues?state=open&per_page=100"
  [ -z "${2:-}" ] || query="$query&labels=$2"
  gh api "$query" --paginate | jq -s -c 'add // [] | map(select(.pull_request | not))
    | map({number, title, url: .html_url, createdAt: .created_at, labels: [.labels[].name],
           login: (.user.login // "ghost"), bot: (.user.type == "Bot")})'
}

say() { printf '%s\n' "$@" >>"$SECTIONS"; }

unreadable() {
  FAILED=$((FAILED + 1))
  echo "couldn't read $1" >&2
  say "Couldn't read $1 this week: the run's log says why." ""
}

# Lists the issues in JSON $1 with jq filter $2 for each entry's note, or
# $3 when there are none
entries() {
  local count
  count="$(jq 'length' <<<"$1")"
  if [ "$count" -eq 0 ]; then
    say "$3" ""
    return 0
  fi
  ITEMS=$((ITEMS + count))
  jq -r --argjson now "$NOW" "$DEFS"'listed('"$2"')' <<<"$1" >>"$SECTIONS"
  say ""
}

tax_figures() {
  local json
  say '## Open `tax-figures` issues' "" \
    "A figure could be wrong, so these come first. Oldest first." ""
  json="$(open_issues "$REPO" tax-figures)" || { unreadable "$REPO's tax-figures issues"; return 0; }
  entries "$(jq -c 'sort_by(.createdAt)' <<<"$json")" '", " + who' "Nothing open."
}

# Issues of $1 from anyone but the owner or a bot, until the owner has
# commented. $2 is "off" for the mirror, whose Issues are meant to be off.
outside_reports() {
  local repo="$1" expect="$2" has json n commenters answered=""
  say "### $repo" ""
  has="$(gh api "repos/$repo" | jq -r '.has_issues')" || { unreadable "$repo"; return 0; }
  if [ "$has" != true ]; then
    if [ "$expect" = off ]; then say "Issues are off, as they should be." ""; else say "Issues are off here." ""; fi
    return 0
  fi
  [ "$expect" != off ] || say "**Issues are on now** (they were off): reports can arrive here." ""
  json="$(open_issues "$repo")" || { unreadable "$repo"; return 0; }
  json="$(jq -c --arg o "$OWNER" 'map(select(.bot | not) | select(.login != $o))' <<<"$json")"
  for n in $(jq -r '.[].number' <<<"$json"); do
    commenters="$(gh api "repos/$repo/issues/$n/comments" --paginate | jq -r '.[].user.login')" ||
      { unreadable "$repo#$n's comments"; continue; }
    grep -Fxq -- "$OWNER" <<<"$commenters" || answered="$answered $n"
  done
  json="$(jq -c --arg nums "$answered" 'map(select(.number as $n | ($nums | split(" ") | index($n | tostring))))
    | sort_by(.createdAt)' <<<"$json")"
  entries "$json" 'if seconds > 604800 then ", **older than a week**" else "" end' "None."
}

outside() {
  say "## Outside reports with no answer" "" \
    "Opened by someone other than $OWNER or a bot, with no comment from $OWNER. An answer is promised within a week. Oldest first." ""
  outside_reports "$REPO" on
  outside_reports "$FORK" on
  outside_reports "$MIRROR" off
}

start9() {
  local json
  say '## Open `start9` issues' "" \
    "What Start9 released or changed that the StartOS package hasn't followed yet, builds that failed, and the package's own to-dos. Oldest first." ""
  json="$(open_issues "$REPO" start9)" || { unreadable "$REPO's start9 issues"; return 0; }
  entries "$(jq -c 'sort_by(.createdAt)' <<<"$json")" '""' "Nothing open."
}

tax_figures
outside
start9

{
  printf 'Updated %s' "$(date -u '+%Y-%m-%d %H:%M UTC')"
  if [ -n "${GITHUB_ACTIONS:-}" ]; then
    printf ' by [the Monday report workflow](%s/%s/actions/runs/%s)' "$GITHUB_SERVER_URL" "$GITHUB_REPOSITORY" "$GITHUB_RUN_ID"
  fi
  printf '. This issue is edited in place each Monday (no notification): close it once it has been read, and next Monday opens a new one.\n\n'
  if [ "$ITEMS" -eq 0 ] && [ "$FAILED" -eq 0 ]; then
    printf '**Nothing needs attention this week.**\n\n'
  fi
  cat "$SECTIONS"
  printf '%s\n' "$SIGNED"
} >"$BODY"

# The open report of ours, if there is one: by this workflow (a bot) or by the
# owner running the script, never an issue someone else gave the same title
existing="$(open_issues "$REPO" | jq -r --arg t "$TITLE" --arg o "$OWNER" \
  'map(select(.title == $t and (.bot or .login == $o))) | (.[0].number // empty)')"

if $DRY; then
  if [ -n "$existing" ]; then echo "WOULD EDIT #$existing: $TITLE"; else echo "WOULD OPEN: $TITLE"; fi
  echo
  cat "$BODY"
elif [ -n "$existing" ]; then
  gh issue edit "$existing" -R "$REPO" --body-file "$BODY"
else
  gh issue create -R "$REPO" --title "$TITLE" --body-file "$BODY"
fi

# A lasting break (a renamed fork, a token that can't read it) fails the run,
# so it doesn't pass unnoticed
[ "$FAILED" -eq 0 ] || exit 1
