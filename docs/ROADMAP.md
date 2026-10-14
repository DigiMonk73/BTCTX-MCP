# Roadmap

Shipped work is in [CHANGELOG.md](CHANGELOG.md). This file lists the features
and larger work coming next; specific to-dos and checks are GitHub issues
(`AGENTS.md`, "Working through GitHub").

## Now: the stable candidate, 1.2.8

The goal (owner, 2026-10-11): a stable release several months before the
2026 filing season, promoted from Start9's Community Beta to the Community
Registry, then maintenance only. The plan and its checklist are #143. The
version plan (owner, 2026-10-14, replacing the 1.2.9-then-1.3.0 plan of
2026-10-13): 1.2.8, with #134's fix, hourly prices, the price redesign and
the security review's fixes, is the stable candidate; it gets the 14 days
on Community Beta and the promotion request. Nothing that changes the
package goes to Start9 during that test, so what's under "Soon" waits for
the maintenance releases after promotion, 1.2.9 first.

- [ ] **The stable-release checklist** (#143; ticked at promotion): every
      blocking item, then 14 days on Community Beta (1.2.8), then the
      promotion request (the owner's OK).
      It includes a full security review, a privacy audit of every request
      the app can make, and a check against current IRS guidance.
- [ ] **Price sources: one clear, simple choice everywhere** (#145): built:
      one price card (your own Mempool, public sites, or nobody, optionally
      through Tor), a status line, confirm once after the update, and each
      value's source shown; StartOS asks at install. Waiting on the owner:
      the landing page's words (#145). Six small pieces of the plan come
      later (#208, under "Soon").

## Soon

- [ ] **The price redesign's six small pieces** (#208; the next release,
      the owner's choice, 2026-10-13): "Recommended" beside "Chosen" in the
      app when StartOS set your own Mempool; a blank value's hint, the Gift
      form's Refresh and the sidebar's Auto price say where the price comes
      from; the sidebar asks "Is Tor running?" when Tor fails; and the AI
      connector says the hour and source of a value it filled.
- [ ] **StartOS keeps only whether a login was set, not the password**
      (#212; the next release, the owner's choice, 2026-10-13), with a
      package migration that drops the stored value.
- [ ] **A gift, donation or lost value left blank is filled from the
      price** (#255; 1.2.9, the owner's choice, 2026-10-14): when it's
      saved, from the BTC price when that hour began (that day's where
      there's no hourly price), shown as coming from the price, as income
      and a spend's proceeds already are; a typed value always wins, and
      with no price source, or no price found, it stays blank. Ledger
      Review lists the gifts, donations and lost coins that have no value,
      including ones saved blank before.
- [ ] **Delete All and Create account ask before wiping the ledger**
      (#256; 1.2.9, the owner's choice, 2026-10-14): a dialog
      that says what goes, offers to download a backup first and deletes
      only once `DELETE` is typed, and a safety copy in the data folder's
      `backups` before the wipe. An empty install isn't warned.
- [ ] **Times on screen in the device's own timezone** (#260; 1.2.9, the
      owner's choice, 2026-10-14): the price card's and Settings' clock
      times as the phone's or computer's clock shows them, like the
      transaction list; the tax timezone keeps deciding the tax year, Form
      8949's dates and the report.
- [ ] **When a broker's Form 1099-DA differs** (#158), before the 2026
      forms are filed (early 2027): the user types the form's proceeds and
      cost for that sale, and Form 8949 shows them with the IRS's code and
      correction (columns (f) and (g)), BitcoinTX's own gain unchanged; the
      report and the guide say when. Generic, not tied to one exchange.
- [ ] Styled dialogs instead of the browser's confirm/prompt (deletes,
      backup password); the one for Delete All and Create account comes
      first (#256, above).
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
      TESTING, `startos/UPDATING.md`), so it waits until the candidate is
      out.

## Later

- [ ] Column-mapping UI for arbitrary exchange CSVs, with saved presets
- [ ] Specific-lot identification (per account, as the IRS has required
      since 2025; for exchange lots it must match the standing order you gave
      the broker). FIFO is the default today.
- [ ] Multi-year reports
- [ ] Ledger integrity audit tool (balances vs lots vs disposals)

## BitcoinTX 2.0 (being considered)

- [ ] **Multiple wallets and exchange accounts**, each tracked as its own
      account with its own cost-basis lots, as the IRS's wallet-by-wallet
      basis rules require from 2025 (Treas. Reg. §1.1012-1(j); Rev. Proc.
      2024-28), and several bank accounts, with transfers between them and
      reports by account. BitcoinTX 1.x is deliberately limited to one
      self-custody wallet and one exchange account (#86). No timeline or
      promise; meanwhile 1.x stays in maintenance.
