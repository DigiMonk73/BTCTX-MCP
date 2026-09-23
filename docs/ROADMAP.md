# Roadmap

Shipped work is in [CHANGELOG.md](CHANGELOG.md). This file lists what's next.

## After v0.8.0

- [ ] Upgrade your real v0.7 database with v0.8.0: backup → start (automatic
      migration) → Recalculate Ledger → compare the 2024/2025 reports with
      the old ones. (Upgrading a v0.7.0 database is covered by tests and CI;
      this checks your actual data.)

## Soon

- [ ] **2026 IRS forms** once the IRS publishes the final revision (the
      `irs-forms-watch` workflow flags it): `python scripts/irs_new_year.py 2026`.
      Expected around Dec 2026–Jan 2027.
- [x] **Schema migrations (Alembic)**: shipped in v0.8.0.
- [x] **Per-transaction 1099-DA override**: shipped in v0.8.0.
- [x] **Reports without side effects**: year-boundary snapshots replay on an
      in-memory copy of the database.
- [ ] **Frontend unit tests** (Vitest) for the transaction form's
      field-to-API mapping, the part most likely to regress.

## Later

- [ ] Column-mapping UI for arbitrary exchange CSVs, with saved presets
- [ ] Specific-lot identification (per account, as the IRS has required
      since 2025; for exchange lots it must match the standing order you gave
      the broker). FIFO is the default today.
- [ ] Multi-year reports
- [ ] Ledger integrity audit tool (balances vs lots vs disposals)
