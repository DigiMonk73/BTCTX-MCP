# Roadmap

Shipped work is in [CHANGELOG.md](CHANGELOG.md). This file lists the features
and larger work coming next; specific to-dos and checks are GitHub issues
(`AGENTS.md`, "Working through GitHub").

## Next release: the stable candidate

The goal (owner, 2026-10-11): a stable release several months before the
2026 filing season, promoted from Start9's Community Beta to the Community
Registry, then maintenance only. The plan and its checklist are #143; the
candidate is the release that carries #134's fix and the work below: 1.2.8
at the least, 1.3.0 as the price screens and the hourly prices change what
users see and how values are made.

- [ ] **The stable-release checklist** (#143; ticked at promotion): every
      blocking item, then 14 days on Community Beta, then the promotion
      request (the owner's OK).
      It includes a full security review, a privacy audit of every request
      the app can make, and a check against current IRS guidance.
- [ ] **Hourly BTC prices, with the hourly history built into the app**
      (#144): each valued transaction priced at its hour from a documented
      worldwide index, one file per year with a checksum; a release script
      adds the newest hours each time a release is made (a convenience, never
      a promise of updates). Saved values change only when the owner applies
      them.
- [ ] **Price sources: one clear, simple choice everywhere** (#145): the
      built-in history always on, one question about newer hours (own
      Mempool, public sites, or nobody), a status line, and each value's
      source shown; a careful plan with mockups, approved before building.
- [ ] **BTC fees and inherited bitcoin** (#163; from the tax-guidance check,
      #150; the owner agreed 2026-10-12):
  - a spend's network fee comes off its proceeds (#157: today the gain is
    a few dollars too high per spend);
  - "Consolidate / move within the same wallet", which records only the
    network fee (#159);
  - an Inherited deposit source: the value at death as cost, always
    long-term, "INHERITED" on Form 8949 (#154).

## Soon

- [ ] **When a broker's Form 1099-DA differs** (#158), before the 2026
      filing season: the user types the form's proceeds and cost for that
      sale, and Form 8949 shows them with the IRS's code and correction
      (columns (f) and (g)), BitcoinTX's own gain unchanged. Generic, not
      tied to one exchange.
- [ ] Styled dialogs instead of the browser's confirm/prompt (deletes,
      backup password).
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
