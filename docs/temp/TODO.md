# To do

Specific items, one line each. Tick `[x]` when done; ticked items are
cleared at the release that ships them (the CHANGELOG has them then).
Plans get their own file in this folder; what's next overall is in
`docs/ROADMAP.md`; the StartOS package's own items are in `startos/TODO.md`.
Rules: `README.md` here.

## Owner

- [ ] Run the password checks on the VM: `cd ~/code/btctx-vm-lab && ./vm.sh start && bash owner-checks.sh` (backup and restore, login cookie, cross-site refusal, password change, login throttle, Reset Login Credentials); results in `scenarios/owner-checks.log`.
- [ ] Finish the 1.2.2 box test on your own server (`startos-box-test-v1.2.2.md`; My Mempool is done). Install 1.2.2-1: the same app, with the real-logo icon.

## Next

- [ ] When Start9 forks the mirror: check `scripts/start9-pull.sh --fork` finds it (if they made a new repository instead, set the repository variable `START9_FORK`). From then on, each release stops if their changes aren't in `startos/` and opens the "Send vX.Y.Z to Start9" issue with the pull-request link (`startos/UPDATING.md`, "After Start9 forks the mirror").
- [ ] The transaction lock flag (`is_locked`) is half-built: nothing in the app can set it (no button; the API ignores it), yet a locked row refuses edits and deletes, while recalculation, Ledger Review's fee fix and Delete All ignore locks. Decide: finish it (a way to lock, respected everywhere, in the CSV export) or remove it.
- [ ] The CSV export writes numbers through a float (`routers/backup.py`, `_csv_number`): exact for every realistic value, but a USD amount over about $67 million with more than two decimals could print a wrong last digit. Format the Decimal directly (low priority).
- [ ] `test_stress_and_forms.py`: `create_tx` swallows failed saves and its random numbers are unseeded, so a failure there can hide or be hard to repeat. Make failures fail and seed the generator (test quality, not an app bug).
- [ ] `frontend/src/hooks/useApiCall.ts` holds only the error-message helper now (the hooks it was named after were never used). Move it to `src/utils/`? Its test file moves with it and only its import line changes; the owner decides, since existing tests were to stay as they are.
