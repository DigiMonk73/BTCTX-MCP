#!/usr/bin/env bash
# Branch rules (AGENTS.md, "Branches"), run by pre-push with git's list of
# pushed refs on stdin: main holds released code and only fast-forwards to
# commits already on GitHub's develop (origin/develop: develop takes changes
# only by pull request, so a commit on a local develop never gets there); it
# is never deleted, rewound or force-pushed. 2.0, the 2.0 build's branch, is
# never deleted, rewound or force-pushed either, and a pin/2.0-* tag is never
# moved or deleted (its ruleset is the real guard; this stops it here first).
# Tested by backend/tests/test_branch_rules.py.
set -euo pipefail

fail() { printf "\n\033[31m✗ push refused: %s\033[0m\n" "$1" >&2; exit 1; }
zero() { [[ "$1" =~ ^0+$ ]]; }

never_rewound() {  # branch, local sha, remote sha
  zero "$2" && fail "$1 can't be deleted"
  if ! zero "$3"; then
    git merge-base --is-ancestor "$3" "$2" 2>/dev/null \
      || fail "$1 can't be rewound or force-pushed (AGENTS.md, Branches)"
  fi
}

while read -r _ local_sha remote_ref remote_sha; do
  case "$remote_ref" in
    refs/heads/main)
      zero "$local_sha" && fail "main can't be deleted"
      git merge-base --is-ancestor "$local_sha" refs/remotes/origin/develop 2>/dev/null \
        || fail "main only takes commits already on GitHub's develop: merge them into develop by pull request, git fetch, then fast-forward main to origin/develop (AGENTS.md, Branches)"
      never_rewound main "$local_sha" "$remote_sha"
      ;;
    refs/heads/2.0)
      never_rewound 2.0 "$local_sha" "$remote_sha"
      ;;
    refs/tags/pin/2.0-*)
      zero "$remote_sha" || [ "$local_sha" = "$remote_sha" ] \
        || fail "${remote_ref#refs/tags/} can't be moved or deleted: a pin stays where it was tagged (AGENTS.md, Branches)"
      ;;
  esac
done
