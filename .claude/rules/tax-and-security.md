---
paths:
  - "backend/*.py"
  - "backend/services/**"
  - "backend/routers/**"
  - "backend/models/**"
  - "backend/migrations/**"
  - "testdata/**"
  - "scripts/*figures*.py"
  - "scripts/seed_ledger.py"
  - "scripts/equivalence_check.py"
  - "mcp_server/btctx_mcp/**"
  - "desktop/*.py"
  - "frontend/src/utils/**"
  - "frontend/src/components/transactionForm/**"
---

# Tax figures, login, the database: read these first

These files can move a tax figure or weaken what protects the owner's
data (`AGENTS.md`, "Before you change…"). Before changing one, read
`docs/TAX-INVARIANTS.md` and `docs/SECURITY-RULES.md` in full, and
`docs/ARCHITECTURE.md`'s "Data model". Each rule there has regression
tests: don't break them. A change here is reviewed as `AGENTS.md`,
"Reviews", says: for tax figures, what the app computes or the database,
the full review, the re-check and every figures check, and a figure
moves only on purpose, with the owner's OK on a plain-words
before-and-after (the figures rule).
