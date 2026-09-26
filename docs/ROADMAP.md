# Roadmap

Shipped work is in [CHANGELOG.md](CHANGELOG.md). This file lists what's next.

## After v0.8.0

- [ ] Upgrade your real v0.7 database with v0.8.0: backup → start (automatic
      migration) → Recalculate Ledger → compare the 2024/2025 reports with
      the old ones. (Upgrading a v0.7.0 database is covered by tests and CI;
      this checks your actual data.)

## v0.9.3

- [ ] **River sends with a network fee (F20)**: does River's "Sent Amount"
      include the fee? Check what the destination received from the
      2026-02-08 send (0.02353629 → fee on top, today's code is right;
      0.02353311 → Sent includes the fee and the importer counts it twice).
      See `HARDENING_FINDINGS.md` F20.
- [ ] **StartOS own node**: offer the local mempool app as "Your own mempool
      server" in Settings → Privacy & network.

## Next: hardening, then a visual polish

Plan, phases and gates: [HARDENING_AND_REDESIGN_PLAN.md](HARDENING_AND_REDESIGN_PLAN.md).

## Soon

- [ ] **2026 IRS forms** once the IRS publishes the final revision (the
      `irs-forms-watch` workflow flags it): `python scripts/irs_new_year.py 2026`.
      Expected around Dec 2026–Jan 2027.
- [x] **Schema migrations (Alembic)**: shipped in v0.8.0.
- [x] **Per-transaction 1099-DA override**: shipped in v0.8.0.
- [x] **Reports without side effects**: year-boundary snapshots replay on an
      in-memory copy of the database.
- [x] **Frontend unit tests** (Vitest): form ↔ API mapping in
      `frontend/src/utils/transactionForm.ts`.

## Later

- [ ] Column-mapping UI for arbitrary exchange CSVs, with saved presets
- [ ] Specific-lot identification (per account, as the IRS has required
      since 2025; for exchange lots it must match the standing order you gave
      the broker). FIFO is the default today.
- [ ] Multi-year reports
- [ ] Ledger integrity audit tool (balances vs lots vs disposals)
