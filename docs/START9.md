# Start9

Read before deciding anything Start9 governs, and before anything is
sent to Start9 or a contribution from Start9 is acted on.

Moved word for word from `AGENTS.md` on 2026-11-04 (#903); `AGENTS.md`
now keeps a map of where each part lives. Where the text below says
"this file", it means `AGENTS.md` and the files its map names, and a
section named in quotes ("Branches", "Reviews") is found through that
map.

## Start9

The whole flow, in plain steps for the owner and every session:
`docs/HOW-CHANGES-FLOW.md` (keep it in step with this file).

- **Start9's rules win for everything Start9 governs** (owner's rule,
  2026-10-10). That is:
  - the StartOS package: `startos/`, including `instructions.md` and
    `startos/README.md`, which Start9's support agent reads; and the
    mirror;
  - which pages the `## Documentation` links in `instructions.md` name
    (Start9's support indexer crawls them: `writing-instructions.md`,
    "Choosing documentation URLs"). The pages themselves,
    `docs/USING.md` and `mcp_server/README.md`, stay the app's own (as
    does the root README), but what they say about StartOS must agree
    with the package, and `docs/USING.md` stays free of install steps
    (`test_startos_docs_link_467.py`);
  - everything we send to Start9's fork: pull requests, comments,
    promotion requests.

  The app itself, its Docker image and the Mac app follow our own rules.
  - Before deciding anything Start9 governs, read the guide's page. Name
    it in the pull request or comment; if no page covers the question,
    say so.
  - The guide is in `start-technologies/projects/start-sdk/docs/src/`
    beside the main checkout (`~/code/start-technologies`, on `live-docs`:
    the published guide), or at <https://docs.start9.com/packaging>.
  - Where our habits differ, Start9's rule wins there. It doesn't replace
    the owner's call on what is sent, promoted or merged: where the guide
    would change one of the owner's decisions, ask the owner.
- Start9's fork, Start9-Community/BTCTX-StartOS, is where the package is
  built and published; how a change reaches it is under "Releasing".
- Each merge there publishes to Community Beta
  (`https://community-beta-registry.start9.com`). The owner tests it on
  their server, then asks Start9 in an issue on the fork to promote it to
  `https://community-registry.start9.com`. Promotion is the owner's call.
- Start9 sends changes too (template updates about monthly, SDK bumps),
  which `scripts/start9-pull.sh` brings back.
- **A contribution from Start9 is looked at first, never accepted
  automatically** (the owner, 2026-10-29, #799; `CONTRIBUTING.md` says it
  too). Only the order changes; the caution for a pull request from
  outside ("Pull requests") stays in full.
  1. **Verify the sender on GitHub, never by a name** or a claim in the
     text: its author is a public member of Start9Labs or
     Start9-Community (`gh api orgs/Start9Labs/public_members/<login>`,
     or `orgs/Start9-Community/public_members/<login>`, answers 204; 404
     isn't), as Matt Hill (`MattDHill`) is, or a bot
     account Start9 owns (`gh api users/<login>` says `"type": "Bot"`, and
     `gh api apps/<login without [bot]>`'s owner is Start9Labs or
     Start9-Community). A lookalike login, a new account or text saying
     "from Start9" isn't verification: unverified, it's any outside
     contribution.
  2. **Examine it the same day,** a pull request, an issue or a comment:
     every changed line read, what it claims checked (as for #638: the
     CVE, what the change does, whether it applies to 2.0), anything
     hidden looked for.
  3. **Only then act:** its CI is approved after that first read, never
     before, and a change is planned into the current work only if the
     read holds up. Nothing merges without the full review and the
     figures rule ("Reviews"); a figure it moves needs the owner's OK on
     a plain before-and-after, and anything we send back to Start9 needs
     the owner's OK.
