# To do

Specific items, one line each. Tick `[x]` when done; ticked items are
cleared at the release that ships them (the CHANGELOG has them then).
Plans get their own file in this folder; what's next overall is in
`docs/ROADMAP.md`; the StartOS package's own items are in `startos/TODO.md`.
Rules: `README.md` here.

## Owner

- [ ] Run the password checks on the VM: `cd ~/code/btctx-vm-lab && ./vm.sh start && bash owner-checks.sh` (backup and restore, login cookie, cross-site refusal, password change, login throttle, Reset Login Credentials); results in `scenarios/owner-checks.log`.
- [ ] Finish the 1.2.2 box test on your own server (`startos-box-test-v1.2.2.md`; My Mempool is done). Install 1.2.3: 1.2.2's app with the code cleanup and two small fixes (the VM tests passed).

## Next

- [ ] The StartOS jobs in `ci.yml` and `release.yml` pin Node 22.23.2: 22.23.3's headers fail to build `diskusage` (a native module of bitcoin-core-startos, pulled in by mempool-startos), "'EmbedderStateTag' does not name a type". Go back to `node-version: 22` once a later Node 22 (or diskusage) builds again: try it on a branch.
- [ ] When Start9 forks the mirror: check `scripts/start9-pull.sh --fork` finds it (if they made a new repository instead, set the repository variable `START9_FORK`). From then on, each release stops if their changes aren't in `startos/` and opens the "Send vX.Y.Z to Start9" issue with the pull-request link (`startos/UPDATING.md`, "After Start9 forks the mirror").
