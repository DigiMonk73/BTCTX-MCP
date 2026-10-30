# Exchange files (made up)

Sample files for the importer for any exchange's CSV (B5b, #567): one or more
for each ready-made mapping, one for each format or case, each written in its
exchange's published format (header, dates, numbers and kinds of row, from the
exchange's help pages and open-source parsers) with **made-up rows only**. None
comes from anyone's real export: this repository is public.
`backend/tests/test_exchange_import_567_mappings.py` works out each file's
figures by hand and checks the import against them
(`backend/tests/test_river_sample_844.py` for River's); other tests
(`test_exchange_rows_said_357.py`, `test_exchange_dollars_655.py`) and the
click-through spec `frontend/e2e/exchange-import-567.e2e.ts` use them too.

To try each one by hand, follow [docs/HAND-TEST.md](../../docs/HAND-TEST.md): a
file added here fails `backend/tests/test_hand_test_guide_844.py` until the
guide lists it (`backend/tests/hand_test_tables.py`, then `make test-pack`).

Owner: the BitcoinTX project (DigiMonk73/BTCTX-MCP); kept by Claude.
