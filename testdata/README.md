# Test data (made up)

Everything here is made up, for tests and for trying BitcoinTX by hand. None of
it comes from anyone's real account: this repository is public.

Owner: the BitcoinTX project (DigiMonk73/BTCTX-MCP); kept by Claude.

| File | What it is |
|---|---|
| `reference_ledger.json` | The one reference test ledger: every kind of transaction, account route and Form 8949 box. Loaded with `scripts/seed_ledger.py`. |
| `reference_prices.json` | The stored prices that ledger's `"priced"` rows take their values from. |
| `reference_figures.json` | Every figure that ledger gives. `backend/tests/test_seed_ledger.py` fails if one moves. |
| `reference_ledger.csv` | That ledger as the app's own CSV export, to import from Settings' screens. `make test-pack` makes it again; `backend/tests/test_reference_csv_844.py` fails when it's stale. |
| `showcase_ledger.json` | A small typical portfolio, for the README's and the landing page's pictures. |
| `exchange_files/` | A sample file or more for each exchange importer (its own [README](exchange_files/README.md)). |

To try these by hand, follow [docs/HAND-TEST.md](../docs/HAND-TEST.md): which
file, where to click, and what you should see.

`reference_ledger.json` and `reference_figures.json` change only with a change
meant to move figures, under the figures rule (AGENTS.md, "Reviews").
