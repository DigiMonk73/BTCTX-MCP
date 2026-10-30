# Roadmap

Shipped work is in [CHANGELOG.md](CHANGELOG.md). This file lists the features
and larger work coming next; specific to-dos and checks are GitHub issues
(`AGENTS.md`, "Working through GitHub").

## Now: 2.0.0

BitcoinTX 2.0.0 is the current version: each wallet, exchange and bank is an
account of its own, each wallet and exchange with its own cost-basis lots. It
reaches StartOS through Start9's Community Beta, then, when the owner asks
Start9 to promote it, its Community Registry. BitcoinTX 1.x gets no more
fixes: its last release, 1.2.10, stays downloadable. No dates are promised.

## Soon

- [ ] **When a broker's Form 1099-DA differs** (#158), before the 2026
      forms are filed (early 2027): the user types the form's proceeds and
      cost for that sale, and Form 8949 shows them with the IRS's code and
      correction (columns (f) and (g)), BitcoinTX's own gain unchanged; the
      report and the guide say when. Generic, not tied to one exchange.
- [ ] Styled dialogs instead of the browser's confirm boxes (deleting a
      transaction, the CSV and River imports, Ledger Review's apply, Reset
      Username & Password, logging out, the AI key), like the one for
      Delete All and Create account (#256, in 1.2.9).
- [ ] **2026 IRS forms** once the IRS publishes the final revision (the
      `irs-forms-watch` workflow opens an issue): `python scripts/irs_new_year.py 2026`.
      Expected around Dec 2026–Jan 2027.
- [ ] **The AI connector follows the app's version** (after Start9's review):
      at start it reads BitcoinTX's version (`/api/health`) and, when it
      differs, restarts itself as `uvx btctx-mcp==<that version>`, so nobody
      edits their AI app's config after updating BitcoinTX. It is never ahead
      of the app (Start9 publishes StartOS updates only after review), and
      PyPI is asked only when the app's version changes. The version-matched
      pin stays the documented setup. Chosen over `uvx btctx-mcp@latest`
      (2026-09-29): that runs ahead of StartOS's app, skips Start9's review
      for the code holding the AI key, and contacts PyPI on every launch.
- [ ] **CHANGELOG notes as separate files, after the stable release**
      (owner, 2026-10-12): each pull request adds its own small note file,
      and the release joins them into `docs/CHANGELOG.md`, so two pull
      requests in flight never conflict there. It changes what reads the
      CHANGELOG (`release.yml`'s version check and release notes,
      `scripts/mirror-startos-release.sh`), the pull request template, and
      the docs that say to edit it (AGENTS.md "Releasing", MAINTENANCE,
      TESTING, `startos/UPDATING.md`), so it waited until 1.2.9 was out.
      Its `startos/UPDATING.md` edit goes to Start9's fork with the
      next release.

## Later

- [ ] Specific-lot identification at an exchange: choosing which coins to
      sell there, matching the standing order you gave the broker. An
      exchange's coins leave oldest first (per-wallet FIFO), the IRS's
      default when you don't identify the coins; in 2.0 you choose them in
      your own wallets.
- [ ] Multi-year reports
- [ ] Ledger integrity audit tool (balances vs lots vs disposals)

## After 2.0 (being considered)

Ideas for a later 2.x version, not promises (the owner, 2026-10-22): kept out
of 2.0, each to be considered once 2.0 is released, with a planning pass and
a feature branch of its own.

- [ ] **Check a wallet against its public key** (#564): a check, not an
      import: the wallet's balance, missing transactions and exact network
      fees, from the owner's own Electrum server or node only, the key never
      stored by default.
- [ ] **Exchange history by API** (#565), with read-only keys; weighed
      against importing the exchange's file (#338).
