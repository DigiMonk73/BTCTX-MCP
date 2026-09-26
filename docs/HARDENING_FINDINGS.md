# Hardening findings (v0.9.2)

Every finding from the hardening plan (`docs/HARDENING_AND_REDESIGN_PLAN.md`),
Phases 1 and 2. Verdicts: **bug** (fix with a test that fails on the old code),
**tax** (a bug whose fix changes tax figures for existing data: owner's OK
first), **ok** (checked, no change), **deferred** (owner's OK recorded).

| ID | What | Where | Evidence | Verdict | Fix / test |
|---|---|---|---|---|---|
| F1 | A "Spent" BTC withdrawal entered in the form with blank proceeds is saved with $0 proceeds, a loss of its whole basis, instead of its market value at the day's price (the rule for unpriced spends). The form sends `proceeds_usd: 0`, which the backend reads as "priced at $0"; only imports send "missing". The form warns but saves. | `utils/transactionForm.ts` `buildTransactionPayload`; `services/transaction.py` `_withdrawal_gross_proceeds` | e2e `create.e2e.ts` "Spent without proceeds…" (marked `test.fail`) | tax | open |
| F2 | "Lost" withdrawals: the transaction records a capital loss of the basis (`realized_gain_usd = −basis`), but Form 8949 excludes Lost as non-taxable. Anything summing `realized_gain_usd` (dashboard, reports) may count a loss the forms don't. | `services/transaction.py:715`, `reports/form_8949.py:99` | e2e `create.e2e.ts` Lost test (locks today's behavior) | open: check every consumer | open |
| F3 | FMV "Refresh" in the form asks for the price of the UTC date of the local time (`toISOString().split("T")[0]`), so an evening entry in the US or a morning entry in Tokyo is priced on the wrong day. | `components/TransactionForm.tsx` `handleRefreshFmv` | code reading | bug | open |
| F4 | The BTC-transfer fee's USD hint uses a hardcoded $30,000 price (`mockBtcPrice`). | `components/TransactionForm.tsx` | code reading | open: check if shown | open |
| F5 | The form sends 0 for every numeric field it doesn't use (`cost_basis_usd` on a Transfer, `fmv_usd` on a Spent withdrawal), so saving a row created by an import or the API turns `null` into `0`. Harmless where 0 and null mean the same; it's the same root cause as F1 where they don't. | `utils/transactionForm.ts` | e2e `edit.e2e.ts` | check with F1 | open |
