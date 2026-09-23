# Roadmap

Shipped work is in [CHANGELOG.md](CHANGELOG.md). This file lists what's next.

## Next release: v0.8.0

Everything under "Unreleased" in the changelog: MCP server, tax timezone,
Form 1099-DA boxes, pure-Python IRS forms, security fixes, calculation fixes.

- [ ] Tag `v0.8.0` on `main` (CI builds the macOS app)
- [ ] Upgrade path verified on a copy of a real v0.7 database: backup →
      Recalculate Ledger → compare the 2024/2025 reports with the old ones

## Soon

- [ ] **2026 IRS forms** once the IRS publishes the final revision (the
      `irs-forms-watch` workflow flags it): `python scripts/irs_new_year.py 2026`.
      Expected around Dec 2026–Jan 2027.
- [x] **Schema migrations (Alembic)**: see CHANGELOG (Unreleased).
- [ ] **Per-transaction 1099-DA override.** A column on Sell transactions
      recording what the broker actually reported (not on a 1099-DA /
      proceeds only / proceeds and basis), for when a real 1099-DA disagrees
      with the default rules in `_broker_reporting()`.
- [ ] **Reports without side effects.** The complete tax report rebuilds the
      ledger to snapshot year-end balances; compute them from lots and
      disposals directly instead.
- [ ] **Frontend unit tests** (Vitest) for the transaction form's
      field-to-API mapping, the part most likely to regress.

## Later

- [ ] Column-mapping UI for arbitrary exchange CSVs, with saved presets
- [ ] Specific-lot identification (per account, as the IRS has required
      since 2025; for exchange lots it must match the standing order you gave
      the broker). FIFO is the default today.
- [ ] Multi-year reports
- [ ] Ledger integrity audit tool (balances vs lots vs disposals)
