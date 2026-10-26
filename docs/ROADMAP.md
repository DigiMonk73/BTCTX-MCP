# Roadmap

Shipped work is in [CHANGELOG.md](CHANGELOG.md). This file lists the features
and larger work coming next; specific to-dos and checks are GitHub issues
(`AGENTS.md`, "Working through GitHub").

## Now: 1.2.10, the first maintenance update of the stable version

1.2.9 is the stable version of 1.x (#143, #369): released on 2026-10-18,
it's on Start9's Community Registry (it serves 1.2.9:0, checked 2026-10-22),
promoted from Community Beta. 1.2.10 fixes four bugs that could make a tax
figure wrong (#535, #549, #581, and a failed save saved later with the next
one, found in #580's review), and every known issue 1.2.9 listed.

Until 2.0 replaces it, 1.x gets maintenance updates (bug and security
fixes, each year's IRS forms, the price history's updates) and the few
small improvements under "Soon" (the owner, 2026-10-17 and 2026-10-18);
new features go into 2.0, below. No dates are promised.

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
      sell there, matching the standing order you gave the broker, once
      brokers support it. An exchange's coins leave oldest first (per-wallet
      FIFO), the IRS's default when you don't identify the coins; 2.0
      chooses them in your own wallets.
- [ ] Multi-year reports
- [ ] Ledger integrity audit tool (balances vs lots vs disposals)

## BitcoinTX 2.0 (planned)

Planned in #251; the build starts on 2026-10-22, on a `2.0` branch of its
own (#251, decision 16). Because it changes how the ledger is
stored, we plan to test 2.0 as a beta on GitHub pre-releases for as long as
it needs; Start9's copy carries only 1.x until 2.0 is ready for Community
Beta, where it stays until the owner asks Start9 to promote it (#251,
decisions 1 and 22).

- [ ] **Multiple wallets and exchange accounts**, each tracked as its own
      account with its own cost-basis lots, as the IRS's wallet-by-wallet
      basis rules require from 2025 (Treas. Reg. §1.1012-1(j); Rev. Proc.
      2024-28), and multiple bank accounts, with transfers between them and
      reports by account. BitcoinTX 1.x is deliberately limited to one
      self-custody wallet and one exchange account (#86). No dates
      promised; meanwhile 1.x stays in maintenance.
- [x] **Choosing which coins leave a wallet** (specific identification,
      Treas. Reg. §1.1012-1(j)(2); #711): on a Transfer out of one of your
      wallets, or a Spent, Gift, Donation or Lost withdrawal from one, with
      the day each choice was saved, in the CSV, the tax report ("Coins you
      chose"), Ledger Review and the AI connector.
- [ ] **An importer for any exchange's CSV**, with ready-made mappings
      for common exchanges and mappings you save, into a ledger that
      already has transactions (#338; the 2.0 plan's B5b, #567).

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
