# Contributing to BitcoinTX

Thanks for helping. BitcoinTX's figures end up on tax forms, so accuracy
and privacy come before everything else, here as in the code.

## Reporting a bug

[Open an issue](https://github.com/DigiMonk73/BTCTX-MCP/issues/new/choose)
with the **Bug report** form, one problem per issue. The
[open bugs](https://github.com/DigiMonk73/BTCTX-MCP/issues?q=is%3Aissue+is%3Aopen+label%3Abug)
are the known issues: check there first.

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

- Every change goes into `develop` by pull request, from a short-lived
  branch. `main` holds released code only.
- CI runs the full test suite, the click-through tests, the Docker and
  StartOS builds and a dependency audit. A pull request merges only once
  they pass, and after a review.
- A bug fix comes with a test that fails without the fix.
- A change to tax figures, the database, the StartOS package or a release
  also needs a before-and-after comparison of what the app produces, and
  the maintainer's approval.
- When a fix changes tax figures, the release notes say what was wrong,
  which versions it affected, and what users should do.

Before writing code, read:

- [README.md](README.md), "Development", to set up and run the tests;
- [docs/CODE_STYLE.md](docs/CODE_STYLE.md) and
  [docs/TESTING.md](docs/TESTING.md);
- [AGENTS.md](AGENTS.md), the project's architecture, tax rules and
  process;
- for the StartOS package, [startos/AGENTS.md](startos/AGENTS.md):
  it follows [Start9's packaging guide](https://docs.start9.com/packaging).

## How BitcoinTX is developed

The maintainer decides what BitcoinTX does. Most of the code, tests and
documentation are written by Claude, an AI by Anthropic, under the
maintainer's direction and review. Anything an AI posts on GitHub is
signed with its name ("— Claude", "— Grok").

## Code of conduct and license

Everyone taking part follows the [code of conduct](CODE_OF_CONDUCT.md).
Contributions are under the project's [MIT license](LICENSE).
