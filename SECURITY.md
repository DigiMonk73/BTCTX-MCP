# Security policy

BitcoinTX holds people's tax records. If you find a security problem,
please report it privately, so it can be fixed before anyone can misuse it.

## Reporting a vulnerability

Use GitHub's private reporting:
**[Report a vulnerability](https://github.com/DigiMonk73/BTCTX-MCP/security/advisories/new)**
(the repository's **Security** tab). Only you and the maintainers see it.

Please don't open a public issue, pull request or discussion about a
security problem.

Include what you can:

- what the problem lets someone do, and to whom;
- the steps to reproduce it;
- the BitcoinTX version and how it's installed (macOS app, StartOS, Docker
  or from source);
- logs or screenshots, **with personal data removed**.

Never send a real ledger, keys, passwords or server addresses. A small test
ledger is enough to show almost any problem. Please test only on your own
install, never on someone else's.

## What happens next

1. We aim to acknowledge your report within 7 days.
2. We confirm the problem and prepare a fix, without saying publicly what
   it fixes.
3. We release a fixed version. On StartOS, we ask Start9 to publish it at
   once.
4. Once the fixed version is available, we publish a GitHub security
   advisory: what the problem was, which versions it affects and what
   users should do. You're credited, unless you'd rather not be.

## Supported versions

Only the latest release gets security fixes. On StartOS, that's the latest
BitcoinTX package in Start9's community registry. Updating is the fix for
every older version.

## Scope

In scope: everything in this repository.

- the BitcoinTX app (server and web interface);
- the AI connector (`btctx-mcp` on PyPI);
- the macOS app;
- the Docker image (`ghcr.io/digimonk73/btctx-mcp`);
- the StartOS package (`startos/`).

Out of scope:

- StartOS itself: report that to Start9.
- The outside services BitcoinTX can ask for prices, and AI providers.

A tax figure that's wrong is a bug, not a security problem: please
[open an issue](https://github.com/DigiMonk73/BTCTX-MCP/issues/new/choose).
Those are fixed first, too.
