# To do

Specific items, one line each. Tick `[x]` when done; ticked items are
cleared at the release that ships them (the CHANGELOG has them then).
Plans get their own file in this folder; what's next overall is in
`docs/ROADMAP.md`; the StartOS package's own items are in `startos/TODO.md`.
Rules: `README.md` here.

## Owner

- [ ] Run the password checks on the VM: `cd ~/code/btctx-vm-lab && ./vm.sh start && bash owner-checks.sh` (backup and restore, login cookie, cross-site refusal, password change, login throttle, Reset Login Credentials); results in `scenarios/owner-checks.log`.
- [ ] Finish the 1.2.2 box test on your own server (`startos-box-test-v1.2.2.md`; My Mempool is done).
- [ ] Send the Start9 submission email to submissions@start9.com (drafted 2026-09-29).

## Next

- [ ] After Start9 forks the mirror: before each release run `scripts/start9-pull.sh`, and after it open a PR from DigiMonk73/BTCTX-StartOS to their fork (`startos/UPDATING.md`).
