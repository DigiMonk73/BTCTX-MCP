#!/usr/bin/env bash
# Branch rules (AGENTS.md, "Branches"), run by pre-push with git's list of
# pushed refs on stdin: main holds released code and only fast-forwards to
# commits already on develop; it is never deleted, rewound or force-pushed.
# Tested by backend/tests/test_branch_rules.py.
set -euo pipefail

fail() { printf "\n\033[31m✗ push refused: %s\033[0m\n" "$1" >&2; exit 1; }

while read -r _ local_sha remote_ref remote_sha; do
  [ "$remote_ref" = refs/heads/main ] || continue
  [[ "$local_sha" =~ ^0+$ ]] && fail "main can't be deleted"
  on_develop=
  for d in refs/heads/develop refs/remotes/origin/develop; do
    git merge-base --is-ancestor "$local_sha" "$d" 2>/dev/null && on_develop=1
  done
  [ -n "$on_develop" ] || fail "main only takes commits already on develop: commit on develop, push it, then fast-forward main (AGENTS.md, Branches)"
  if ! [[ "$remote_sha" =~ ^0+$ ]]; then
    git merge-base --is-ancestor "$remote_sha" "$local_sha" 2>/dev/null \
      || fail "main can't be rewound or force-pushed (AGENTS.md, Branches)"
  fi
done
