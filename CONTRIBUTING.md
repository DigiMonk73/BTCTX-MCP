# Contributing to BitcoinTX

Thanks for helping. BitcoinTX's figures end up on tax forms, so accuracy
and privacy come before everything else, here as in the code.

## Reporting a bug

[Open an issue](https://github.com/DigiMonk73/BTCTX-MCP/issues/new/choose)
with the **Bug report** form, one problem per issue. The
[open bugs](https://github.com/DigiMonk73/BTCTX-MCP/issues?q=is%3Aissue+is%3Aopen+label%3Abug)
are the known issues: check there first. A new report is labelled
`unconfirmed` until it has been reproduced, then `bug`.

- **Never post personal data.** That means no real ledger figures, Bitcoin
  addresses or transaction ids, keys, passwords, server addresses, or
  screenshots of a real ledger. Issues are public. A small test ledger
  that shows the problem is best.
- **A wrong tax figure?** Say so in the form. These bugs are labelled
  `tax-figures` and fixed first.
- **A security problem?** Don't open an issue: follow
  [SECURITY.md](SECURITY.md).

Every bug the maintainers find themselves is filed as a public issue too,
so the list of known issues is complete.

## Suggesting a feature

Use the **Feature request** form: the problem first, then your idea.

## How changes are made

- Every change goes into `staging` by pull request, from a short-lived
  branch: open yours against `staging`, not `develop` or `main`.
  `develop` takes `staging` once a day, after the whole suite has run on
  everything together; `main` holds released code only.
- CI runs the full test suite, the frontend's tests, the StartOS checks
  and a dependency audit on your pull request (once the maintainer has
  approved it: "Pull requests from outside", below), and the
  click-through tests and the Docker and StartOS builds once it's in
  `staging`. A pull request merges only once its checks pass, and after a
  review.
- A bug fix comes with a test that fails without the fix.
- A change to tax figures, the database, the StartOS package or a release
  needs the maintainer's approval, and a before-and-after comparison of
  what the app produces whenever figures could move.
- When a fix changes tax figures, the release notes say what was wrong,
  which versions and which tax years it affected, and what users should do.

Before writing code, read:

- [README.md](README.md), "Development", to set up and run the tests;
- [docs/CODE_STYLE.md](docs/CODE_STYLE.md) and
  [docs/TESTING.md](docs/TESTING.md);
- [AGENTS.md](AGENTS.md), the project's architecture, tax rules and
  process;
- for the StartOS package, [startos/AGENTS.md](startos/AGENTS.md):
  it follows [Start9's packaging guide](https://docs.start9.com/packaging).

## Pull requests from outside

BitcoinTX's figures go on tax returns and its code runs on people's own
servers, so a pull request from outside the project is handled with care:

- **We take only tests or documentation from outside,** after reading
  every line, and merge them exactly as reviewed.
- **For anything else** (the app's code, CI, dependencies, the build, the
  StartOS package or the tax logic), if we take the change, we write it
  ourselves, from your pull request's idea. A bug report or an idea is
  just as welcome.
- **CI runs on a pull request from outside only after the maintainer
  approves it,** each time: GitHub holds its checks until then.
- **A contribution from Start9 is looked at first, the same day, but never
  accepted automatically.** It counts as Start9's only when GitHub shows
  it, never by a name or a claim in its text: its author is a public
  member of the Start9Labs or Start9-Community organization, or a bot
  account that one of them owns. Every line is read and every claim
  checked before its CI is approved, and it then gets the same review as
  any change: the rules above still apply, only the order changes.

## How BitcoinTX is developed

The maintainer decides what BitcoinTX does. Most of the code, tests and
documentation are written by Claude, an AI by Anthropic, under the
maintainer's direction and review. Anything an AI posts on GitHub is
signed with its name ("— Claude", "— Grok").

## Code of conduct and license

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).
Contributions are under the project's [MIT license](LICENSE).
