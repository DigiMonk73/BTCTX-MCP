# Roadmap

Shipped work is in [CHANGELOG.md](CHANGELOG.md). This file lists what's next.

## Owner check

- [ ] Upgrade your real v0.7 database with the current version: backup →
      start (automatic migration) → Settings → Ledger Review → Recalculate
      Ledger → compare the 2024/2025 reports with the old ones. (Upgrading a
      v0.7.0 database is covered by tests and CI; this checks your actual
      data.)

## Next release

- [ ] **River sends with a network fee (F20)**: does River's "Sent Amount"
      include the fee? Check what the destination received from the
      2026-02-08 send (0.02353629 → fee on top, today's code is right;
      0.02353311 → Sent includes the fee and the importer counts it twice).
      See `HARDENING_FINDINGS.md` F20.
- [ ] Styled dialogs instead of the browser's confirm/prompt (deletes,
      backup password).

## Soon

- [ ] **2026 IRS forms** once the IRS publishes the final revision (the
      `irs-forms-watch` workflow flags it): `python scripts/irs_new_year.py 2026`.
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
